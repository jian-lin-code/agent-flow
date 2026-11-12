import asyncio
import html
import re
import time
import zipfile
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Tuple, List, Dict
from urllib.parse import unquote

import httpx
import aiofiles

from app.events.document_progress import emit
from app.utils.image_processor import get_image_processor
from app.utils.logger import logger
from app.core.config import settings
from app.utils.minio_client import get_minio_storage

# 统一的图片引用匹配：
# 1) Markdown 内联式  ![alt](images/x.jpg "title")
# 2) Markdown 引用式  ![alt][ref] + [ref]: images/x.jpg
# 3) HTML <img src="images/x.jpg">（MinerU 在表格单元格里输出的是这种）
_MD_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\(\s*<?(?P<src>[^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
_MD_REF_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\[(?P<ref>[^\]]*)\]")
_MD_REF_DEF_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]:\s*(?P<src>\S+)", re.MULTILINE)
_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_ATTR_RE = re.compile(r"""\b(?:src|data-src)\s*=\s*["'](?P<src>[^"']+)["']""", re.IGNORECASE)
_ALT_ATTR_RE = re.compile(r"""\balt\s*=\s*["'][^"']*["']""", re.IGNORECASE)


class MinerUService:
    def __init__(self):
        self.base_url = settings.MINERU_BASE_URL
        self.api_token = settings.MINERU_API_TOKEN
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

        # 设置本地存放输出文件的目录
        self.output_dir = Path(__file__).resolve().parent.parent.parent.parent / getattr(settings, "MINERU_OUTPUT_DIR")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.timeout_seconds = 600  # 最大超时时间（10分钟）
        self.poll_interval = 3  # 轮询间隔（3秒）

        # 设置允许的图片格式
        self.image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

        self.image_processor = get_image_processor()
        self.minio_client = get_minio_storage()

    async def convert_pdf_to_md(self, pdf_bytes: bytes, filename: str, ctx: Dict) -> str:
        """核心方法：传入 PDF 字节流，返回带有 MinIO 图片链接的 Markdown 字符串。"""
        pdf_stem = Path(filename).stem
        task_output_dir = self.output_dir / pdf_stem

        # 1. 初始化工作目录
        if task_output_dir.exists():
            shutil.rmtree(task_output_dir)
        task_output_dir.mkdir(parents=True, exist_ok=True)

        await emit("开始执行结构化解析", ctx=ctx, stage="parsing")

        try:
            # 2. 请求上传链接
            signed_url, batch_id = await self._get_upload_url(filename, ctx)

            # 3. 上传 PDF 文件流
            await self._upload_file(signed_url, pdf_bytes, ctx)

            # 4. 轮询结果
            zip_url = await self._poll_result(batch_id, ctx)

            # 5. 下载并解压 ZIP
            md_path, md_content = await self._download_and_extract(zip_url, task_output_dir, pdf_stem, ctx)

            # 6. 处理图片 (扫描 + 组装上下文)
            target_images = await self._process_images_and_md(md_path, md_content, ctx)

            if target_images:
                # 图片上传与摘要生成互不依赖：上传先跑起来，摘要生成完再合并，
                # 长文档能省掉串行上传的等待时间。
                upload_task = asyncio.create_task(
                    self.minio_client.upload_images_batch(target_images, ctx=ctx)
                )
                try:
                    # 7. 调用多模态大模型生成图片摘要（并发）
                    summaries = await self._generate_summaries(md_path.stem, target_images, ctx)
                    urls = await upload_task
                except Exception:
                    upload_task.cancel()
                    raise

                # 8. 替换 MD 图片路径并填充摘要
                return await self._upload_and_replace(target_images, summaries, md_content, ctx, urls)

            await emit("文档中没有需要处理的图片，跳过图片流水线", ctx=ctx, stage="parsing")
            return md_content

        finally:
            # 无论成功失败，统一在 finally 中清理本地临时目录，防止磁盘占满
            pass
            # await self._clean_task_output_dir(task_output_dir, ctx)

    async def _get_upload_url(self, filename: str, ctx: Dict) -> tuple[str, str]:
        """1. 请求 MinerU API，获取用于上传文件的预签名 URL 和任务 batch_id"""
        await emit("正在向云端请求上传凭证", ctx=ctx, stage="parsing")

        url = f"{self.base_url}/file-urls/batch"
        data = {"files": [{"name": filename}], "model_version": "vlm"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=self.headers, json=data, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            if result.get("code") != 0:
                err_msg = str(result)[:200]
                await emit(f"获取上传凭证失败：{err_msg}", ctx=ctx, stage="parsing", level="error")
                raise RuntimeError(f"获取上传链接失败: {err_msg}")

            await emit(f"凭证获取成功（任务 {batch_id_short(result['data']['batch_id'])}）", ctx=ctx, stage="parsing")
            return result["data"]["file_urls"][0], result["data"]["batch_id"]

    async def _upload_file(self, signed_url: str, pdf_bytes: bytes, ctx: Dict):
        """2. 将 PDF 字节流上传到预签名 URL"""
        size_mb = len(pdf_bytes) / (1024 * 1024)
        await emit(f"正在上传文档至云端（{size_mb:.2f} MB）", ctx=ctx, stage="parsing")

        async with httpx.AsyncClient() as client:
            # 上传到预签名 URL 时，不要带 Authorization 头
            resp = await client.put(signed_url, content=pdf_bytes, timeout=60)
            if resp.status_code in (200, 201):
                await emit("文档上传成功，等待云端排队解析", ctx=ctx, stage="parsing", progress=5)
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                await emit(f"文档上传失败：{err_msg}", ctx=ctx, stage="parsing", level="error")
                raise RuntimeError(f"文件上传失败，{err_msg}")

    async def _poll_result(self, batch_id: str, ctx: Dict) -> str:
        """3. 轮询任务状态，直到解析完成，返回结果 ZIP 包的下载链接"""
        poll_url = f"{self.base_url}/extract-results/batch/{batch_id}"
        start_time = asyncio.get_event_loop().time()

        await emit("云端解析排队中，开始轮询进度", ctx=ctx, stage="parsing", progress=8)
        last_state = None

        async with httpx.AsyncClient() as client:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > self.timeout_seconds:
                    await emit(f"云端解析超时（超过 {self.timeout_seconds} 秒）", ctx=ctx, stage="parsing", level="error")
                    raise TimeoutError(f"MinerU 解析超时 ({self.timeout_seconds}s)")
                try:
                    resp = await client.get(poll_url, headers=self.headers, timeout=10)
                    resp.raise_for_status()
                    poll_data = resp.json()

                    if poll_data.get("code") != 0:
                        err_msg = str(poll_data)[:200]
                        await emit(f"轮询返回异常：{err_msg}", ctx=ctx, stage="parsing", level="error")
                        raise RuntimeError(f"业务错误: {err_msg}")

                    result_item = poll_data["data"]["extract_result"][0]
                    state = result_item["state"]

                    if state == "done":
                        await emit(f"云端解析完成（耗时 {int(elapsed)}s），正在获取结果包", ctx=ctx, stage="parsing", progress=25)
                        return result_item["full_zip_url"]
                    elif state == "failed":
                        err_msg = result_item.get('err_msg', '未知错误')
                        await emit(f"云端解析失败：{err_msg}", ctx=ctx, stage="parsing", level="error")
                        raise RuntimeError(f"解析失败: {err_msg}")
                    else:
                        # 状态没变时不重复刷屏，只有状态变化时才推送一条
                        if state != last_state:
                            logger.debug(f"[MinerU] 处理中... 状态: {state}")
                            await emit(f"云端处理状态：{state}（已等待 {int(elapsed)}s）", ctx=ctx, stage="parsing", progress=15)
                            last_state = state
                        await asyncio.sleep(self.poll_interval)

                except httpx.RequestError as e:
                    logger.warning(f"[MinerU] 网络波动，重试中: {e}")
                    await emit("网络波动，正在重试轮询", ctx=ctx, stage="parsing", level="warn")
                    await asyncio.sleep(self.poll_interval)

    async def _download_and_extract(self, zip_url: str, target_dir: Path, pdf_stem: str, ctx: Dict) -> tuple[Path, str]:
        """4. 下载 ZIP 并解压，返回生成的 md 文件路径"""
        zip_path = target_dir / "result.zip"

        # 1. 下载 ZIP
        await emit("正在拉取解析结果压缩包", ctx=ctx, stage="parsing", progress=28)
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", zip_url, timeout=120) as resp:
                resp.raise_for_status()
                async with aiofiles.open(zip_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        await f.write(chunk)
        await emit("结果压缩包获取完成", ctx=ctx, stage="parsing", progress=33)

        # 2. 解压 ZIP
        await emit("正在解压解析结果", ctx=ctx, stage="parsing", progress=35)

        # 确保目录存在（因为可能被前面的异常清空或不存在）
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(target_dir)
        except FileExistsError as e:
            # 针对 Windows 特有的同名文件已存在报错
            logger.warning(f"[解析] 解压遇到文件冲突 (WinError 183)，尝试清理后重试: {e}")
            # 清理解压出来的旧文件，但保留刚下载的 result.zip
            for item in target_dir.iterdir():
                if item.name != "result.zip":
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

            # 重新解压
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(target_dir)

        # 3. 查找 md 文件
        md_files = list(target_dir.rglob("full.md"))
        if not md_files:
            md_files = list(target_dir.rglob("*.md"))
        if not md_files:
            await emit("解压完成，但未找到 Markdown 文件", ctx=ctx, stage="parsing", level="error")
            raise FileNotFoundError("解压后未找到 Markdown 文件")

        old_md_path = md_files[0]
        new_md_path = target_dir / f"{pdf_stem}.md"
        old_md_path.rename(new_md_path)

        async with aiofiles.open(new_md_path, mode='r', encoding='utf-8') as f:
            md_content = await f.read()

        return new_md_path, md_content

    # ------------------------------------------------------------------
    # 图片引用解析
    # MinerU 的输出里图片有三种写法，旧实现只认第一种，于是：
    # - 表格单元格里的 <img src="images/x.jpg"> 永远匹配不到（既没有摘要也不替换，
    #   最终以本地死链的形式进了切块）；
    # - 匹配和替换各写一份正则，容易出现"扫描时匹配到了、替换时匹配不上"的错位。
    # 这里统一成一套规则：一次扫描收集引用，一次替换消费结果。
    # ------------------------------------------------------------------
    @staticmethod
    def _image_key(src: str) -> str:
        """把图片引用地址归一化成文件名，用于和 images 目录里的文件对齐。"""
        cleaned = (src or "").split("?")[0].split("#")[0].strip().strip("<>\"'")
        cleaned = cleaned.replace("\\", "/")
        return unquote(Path(cleaned).name)

    @classmethod
    def _iter_image_refs(cls, md_content: str) -> list[tuple[int, int, str]]:
        """扫描 md 中所有图片引用的 (start, end, src)，按出现顺序返回。"""
        refs: list[tuple[int, int, str]] = []
        for match in _MD_IMAGE_RE.finditer(md_content):
            refs.append((match.start(), match.end(), match.group("src")))
        for match in _HTML_IMAGE_RE.finditer(md_content):
            src_match = _SRC_ATTR_RE.search(match.group(0))
            if src_match:
                refs.append((match.start(), match.end(), src_match.group("src")))
        refs.sort(key=lambda item: item[0])
        return refs

    @classmethod
    def _collect_image_context(cls, md_content: str, context_len: int = 100) -> dict[str, tuple[str, str]]:
        """一次性建立「图片文件名 -> 上下文」映射，避免每张图都全文扫一遍。"""
        contexts: dict[str, tuple[str, str]] = {}
        for start, end, src in cls._iter_image_refs(md_content):
            key = cls._image_key(src)
            if not key or key in contexts:
                continue
            contexts[key] = (
                md_content[max(0, start - context_len):start],
                md_content[end:min(len(md_content), end + context_len)],
            )
        return contexts

    @staticmethod
    def _is_local_ref(src: str) -> bool:
        """只在本地产物里有效的相对路径（如 images/xxx.jpg）在 MinIO 上必然 404。"""
        lowered = (src or "").lower()
        return not lowered.startswith(("http://", "https://", "data:", "//"))

    @staticmethod
    def _is_decorative(image_path: Path, min_bytes: int = 4096, max_area: int = 400 * 300) -> bool:
        """体积和尺寸都很小的图片多为图标、分隔线，不值得调用多模态模型。"""
        try:
            if image_path.stat().st_size > min_bytes:
                return False
            from PIL import Image
            with Image.open(image_path) as im:
                width, height = im.size
            return width * height <= max_area
        except Exception:
            return False

    async def _process_images_and_md(self, md_path: Path, md_content: str, ctx: Dict) -> list[tuple[str, Path, tuple[str, str]]] | None:
        """5. 扫描图片文件夹，过滤出「支持格式 + MD中实际引用」的图片"""
        images_dir = md_path.parent / "images"
        if not images_dir.exists() or not images_dir.is_dir():
            await emit("未发现图片目录，跳过图片处理", ctx=ctx, stage="parsing")
            return None

        contexts = self._collect_image_context(md_content)
        target_images: list[tuple[str, Path, tuple[str, str]]] = []
        decorative = 0

        for img_path in sorted(images_dir.glob("*")):
            if not img_path.is_file() or img_path.suffix.lower() not in self.image_extensions:
                continue
            context = contexts.get(img_path.name)
            if not context:
                # 图片文件存在但正文没引用（MinerU 会把页眉页脚图一起打包），不参与处理
                continue
            if self._is_decorative(img_path):
                decorative += 1
                continue
            target_images.append((img_path.name, img_path, context))

        await emit(
            f"图片扫描完成：正文引用 {len(contexts)} 处，{len(target_images)} 张待生成摘要"
            + (f"，跳过装饰性小图 {decorative} 张" if decorative else ""),
            ctx=ctx,
            stage="parsing",
            progress=40,
        )
        return target_images

    async def _generate_summaries(self, doc_stem: str, target_images: list[Tuple[str, Path, tuple[str, str]]],
                                  ctx: Dict) -> Dict[str, str]:
        """6. 并发生成图片摘要（同一张图只调用一次模型）"""
        total = len(target_images)
        concurrency = max(1, settings.IMAGE_SUMMARY_CONCURRENCY)
        await emit(
            f"开始为 {total} 张图片生成 AI 摘要（并发 {concurrency}）",
            ctx=ctx,
            stage="parsing",
            progress=40,
        )

        semaphore = asyncio.Semaphore(concurrency)
        summaries: Dict[str, str] = {}
        digest_cache: Dict[str, str] = {}
        state = {"done": 0, "reused": 0}
        started_at = time.monotonic()
        last_report_at = 0.0
        report_every = max(1, total // 20)

        async def run_one(idx: int, img_file: str, image_path: Path, context: tuple[str, str]) -> None:
            nonlocal last_report_at
            async with semaphore:
                try:
                    async with aiofiles.open(image_path, "rb") as f:
                        img_bytes = await f.read()
                except Exception as e:
                    logger.error(f"[图片] 读取本地图片失败: {e}")
                    img_bytes = b""

                digest = self.image_processor.digest(img_bytes) if img_bytes else ""
                if digest and digest in digest_cache:
                    # 同一文档里重复出现的图片（logo、页眉图）直接复用摘要
                    summary = digest_cache[digest]
                    state["reused"] += 1
                else:
                    await self.image_processor.apply_rate_limit(ctx=ctx)
                    img_format = image_path.suffix.replace(".", "").lower() or "jpeg"
                    if img_format == "jpg":
                        img_format = "jpeg"
                    summary = await self.image_processor.generate_image_summary(
                        image_data=img_bytes,
                        img_format=img_format,
                        doc_stem=doc_stem,
                        image_content=context,
                        ctx=ctx,
                        label=f"图{idx}",
                    )
                    if digest:
                        digest_cache[digest] = summary

                summaries[img_file] = summary

                state["done"] += 1
                now = time.monotonic()
                if state["done"] == total or state["done"] % report_every == 0 or now - last_report_at >= 3:
                    last_report_at = now
                    elapsed = max(now - started_at, 0.001)
                    speed = state["done"] / elapsed
                    remain = (total - state["done"]) / speed if speed > 0 else 0
                    await emit(
                        f"图片摘要 {state['done']}/{total}"
                        f"（{int(state['done'] * 100 / total)}%） · {speed:.1f} 张/秒"
                        f" · 预计剩余 {remain:.0f}s",
                        ctx=ctx,
                        stage="parsing",
                        progress=40 + int(state["done"] * 50 / total) if total else 40,
                    )

        await asyncio.gather(
            *(
                run_one(idx, img_file, image_path, context)
                for idx, (img_file, image_path, context) in enumerate(target_images, start=1)
            )
        )

        elapsed = time.monotonic() - started_at
        extra = f"，重复图片复用 {state['reused']} 张" if state["reused"] else ""
        await emit(
            f"图片摘要生成完成：共 {total} 张，耗时 {elapsed:.1f}s{extra}",
            ctx=ctx,
            stage="parsing",
            progress=90,
        )
        return summaries

    async def _upload_and_replace(self, target_images: List[Tuple[str, Path, Tuple[str, str]]],
                                  summaries: Dict[str, str], md_content: str, ctx: Dict,
                                  urls: Dict[str, str] | None = None):
        """7. 上传图片并合并信息，替换 Markdown"""

        # 1. 批量上传图片至 MinIO（路径使用对外 uid）
        if urls is None:
            urls = await self.minio_client.upload_images_batch(target_images, ctx=ctx)

        # 2. 合并图片摘要和 URL
        image_info = await self._merge_summary_and_url(summaries, urls, ctx)

        # 3. 替换 MD 内容中的本地图片引用
        md_content = await self._process_md_file(md_content, image_info, ctx)

        return md_content

    async def _merge_summary_and_url(self, summaries: Dict[str, str], urls: Dict[str, str],
                                     ctx: Dict) -> Dict[str, Tuple[str, str]]:
        image_info = self.image_processor.merge_summary_and_url(summaries, urls)

        success_count = len(image_info)
        drop_count = len(summaries) - success_count

        if drop_count > 0:
            await emit(
                f"图片信息校验：有效 {success_count} 张，上传失败 {drop_count} 张",
                ctx=ctx,
                stage="parsing",
                level="warn",
            )
        return image_info

    async def _process_md_file(self, md_content: str, image_info: Dict[str, Tuple[str, str]],
                               ctx: Dict) -> str:
        """替换 MD 内容中的本地图片引用为「摘要 + MinIO 链接」"""
        stats = {"replaced": 0, "missing": 0}

        def replace_inline(match: re.Match) -> str:
            src = match.group("src")
            info = image_info.get(self._image_key(src))
            if info:
                stats["replaced"] += 1
                return f"![{info[0]}]({info[1]})"
            if self._is_local_ref(src):
                # 没能上传成功的本地图片留着就是死链（MinIO 上没有 images/ 目录）
                stats["missing"] += 1
                return ""
            return match.group(0)

        md_content = _MD_IMAGE_RE.sub(replace_inline, md_content)
        md_content = self._replace_reference_images(md_content, image_info, stats)
        md_content = _HTML_IMAGE_RE.sub(
            lambda match: self._replace_html_image(match, image_info, stats), md_content
        )

        # 删掉空引用后可能留下连续空行，压缩一下避免切块里出现大片空白
        md_content = re.sub(r"\n{3,}", "\n\n", md_content)

        if stats["replaced"] == 0 and stats["missing"] == 0:
            await emit(
                "未在正文中定位到任何图片引用，跳过图片替换",
                ctx=ctx,
                stage="parsing",
                level="warn",
            )
            return md_content

        message = f"图文替换完成：写入 {stats['replaced']} 处图片摘要"
        if stats["missing"]:
            message += f"，丢弃 {stats['missing']} 处失效本地引用"
        await emit(
            message,
            ctx=ctx,
            stage="parsing",
            progress=95,
            level="warn" if stats["missing"] else "info",
        )
        return md_content

    def _replace_reference_images(self, md_content: str, image_info: Dict[str, Tuple[str, str]],
                                  stats: Dict[str, int]) -> str:
        """处理 ![alt][ref] + [ref]: images/x.jpg 这种引用式写法。"""
        definitions = {name.lower(): src for name, src in _MD_REF_DEF_RE.findall(md_content)}
        if not definitions:
            return md_content

        def replace_ref(match: re.Match) -> str:
            ref = (match.group("ref") or match.group("alt") or "").strip().lower()
            src = definitions.get(ref)
            if not src:
                return match.group(0)
            info = image_info.get(self._image_key(src))
            if info:
                stats["replaced"] += 1
                return f"![{info[0]}]({info[1]})"
            if self._is_local_ref(src):
                stats["missing"] += 1
                return ""
            return match.group(0)

        return _MD_REF_IMAGE_RE.sub(replace_ref, md_content)

    def _replace_html_image(self, match: re.Match, image_info: Dict[str, Tuple[str, str]],
                            stats: Dict[str, int]) -> str:
        """处理 <img src="images/x.jpg">（MinerU 表格单元格里的图片）。

        表格里保留 HTML 标签比换成 Markdown 更安全：alt 里的 | 会被当成列分隔符。
        """
        tag = match.group(0)
        src_match = _SRC_ATTR_RE.search(tag)
        if not src_match:
            return tag

        src = src_match.group("src")
        info = image_info.get(self._image_key(src))
        if not info:
            if self._is_local_ref(src):
                stats["missing"] += 1
                return ""
            return tag

        stats["replaced"] += 1
        alt, url = info
        safe_alt = html.escape(alt, quote=True)
        new_tag = _SRC_ATTR_RE.sub(f'src="{url}"', tag, count=1)
        if _ALT_ATTR_RE.search(new_tag):
            new_tag = _ALT_ATTR_RE.sub(f'alt="{safe_alt}"', new_tag, count=1)
        else:
            new_tag = re.sub(r"<img\b", f'<img alt="{safe_alt}"', new_tag, count=1, flags=re.IGNORECASE)
        return new_tag

    async def _clean_task_output_dir(self, task_output_dir: Path, ctx: Dict):
        """清除当前PDF任务对应的输出目录"""
        if not task_output_dir.exists() or not task_output_dir.is_dir():
            return

        try:
            shutil.rmtree(task_output_dir)
            logger.info(f"[MinerU] 成功清理本地临时目录：{task_output_dir}")
        except Exception as e:
            logger.exception(f"[MinerU] 清理目录失败 {task_output_dir}")
            await emit("临时目录清理失败", ctx=ctx, stage="parsing", level="warn")


def batch_id_short(batch_id: str) -> str:
    return f"{batch_id[:8]}…" if batch_id else "-"


@lru_cache(maxsize=1)
def get_mineru_service() -> MinerUService:
    return MinerUService()
