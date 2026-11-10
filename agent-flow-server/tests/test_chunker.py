import asyncio
import json
from pathlib import Path
from unittest import result

from app.rag.chunker import get_document_chunker
from app.utils.logger import logger


async def main(): # 👈 包一个异步函数
    # 1. 读取文件
    file = Path(__file__).parent / "docs" / "测试文档切分.md"
    content = file.read_text(encoding="utf-8")

    parser = get_document_chunker()

    # 2. 👇 加上 await 拿真正的返回结果
    chunks = await parser.process(
        content=content,
        filename="测试文档切分.md",
        ctx={"document_uid": "uid-test-0001"}
    )

    print(f"总切片数: {len(chunks)}")

    # 3. 打印切片详情
    result_json = json.dumps(chunks,indent=4,ensure_ascii=False)
    logger.info(f'result:{result_json}')

if __name__ == '__main__':
    asyncio.run(main()) # 👈 用 asyncio 启动