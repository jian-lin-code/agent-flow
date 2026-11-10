import asyncio
import os
from app.services.expense_pre_review_service import ExpenseVisionService


async def test_recognize_real_invoice():
    # 1. 准备测试图片路径
    image_path = r"C:\Users\xiaojianlin\Desktop\ui\73f3c2ba-dfbb-4a90-9b08-2f6ff8210966.png"  # 请确保项目根目录下有这张图片
    if not os.path.exists(image_path):
        print(f"❌ 找不到测试图片: {image_path}，请先放一张发票图片。")
        return

    # 2. 读取图片并确定 MIME 类型
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # 根据后缀简单判断 content_type
    content_type = "image/jpeg" if image_path.endswith(".jpg") else "image/png"

    # 3. 实例化 Service 并调用
    print("⏳ 正在调用视觉模型识别发票，请稍候...")
    service = ExpenseVisionService()

    try:
        result = await service.recognize_image(
            image_bytes=image_bytes,
            content_type=content_type
        )

        print("\n✅ 识别成功！结构化结果如下：")
        # 使用 model_dump_json 方便打印查看
        print(result.model_dump_json(indent=2))

        # 针对你的业务逻辑，可以做个简单断言（看具体模型定义）
        if hasattr(result, "total_amount"):
            print(f"\n核心提取测试 -> 价税合计: {result.total_amount}")

    except ValueError as e:
        print(f"❌ 参数校验失败: {e}")
    except Exception as e:
        print(f"❌ 模型调用或解析失败: {e}")


async def test_recognize_from_minio():
    # 1. 准备测试参数
    # ⚠️ 请替换为你系统里真实存在的 MinIO 对象路径
    # 比如你在 upload_expense_item_attachment 里存的 object_name
    test_object_name = "business-tasks/339defde-538a-4ed8-a777-c1002954f71a/9b71f0b6-f79b-4902-8a03-163030950b83/cd999bc58ee44465bd54b55dc84d98e5.jpg"

    # 根据你的文件实际类型填写
    test_content_type = "image/jpeg"

    print(f"⏳ 正在从 MinIO 下载并识别: {test_object_name}")

    service = ExpenseVisionService()

    try:
        # 2. 调用目标函数
        result = await service.recognize_from_minio(
            object_name=test_object_name,
            content_type=test_content_type,
        )

        # 3. 打印结果
        print("\n✅ 识别成功！提取到的结构化数据如下：")
        print(result.model_dump_json(indent=2))

    except ValueError as e:
        print(f"\n❌ 参数或文件内容错误: {e}")
    except Exception as e:
        print(f"\n❌ 识别过程发生异常: {e}")
if __name__ == "__main__":
    # asyncio.run(test_recognize_real_invoice())
    asyncio.run(test_recognize_from_minio())