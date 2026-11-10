
import asyncio

from sqlalchemy import inspect, text

from app.core import database
from app.core.base import Base
from app.models.expense_claim import (
    ExpenseClaim,
    ExpenseItem,
    Attachment,
    BusinessTask,
)
from app.models.workflow import WorkflowRun, RunStep
from app.utils.logger import logger


async def update_database():
    # 1. 初始化数据库引擎
    database.init_db_engine()

    try:
        if database.engine is None:
            raise RuntimeError("数据库引擎初始化失败")

        async with database.engine.begin() as conn:

            # 2. 创建不存在的表
            await conn.run_sync(Base.metadata.create_all)

            logger.info("数据库表检查及创建完成")

            # 3. 检查 workflow_runs 表是否存在
            table_exists = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).has_table(
                    "workflow_runs"
                )
            )

            if not table_exists:
                raise RuntimeError("workflow_runs 表不存在")

            # 4. 检查 business_task_id 字段
            columns = await conn.run_sync(
                lambda sync_conn: {
                    column["name"]
                    for column in inspect(sync_conn).get_columns(
                        "workflow_runs"
                    )
                }
            )

            if "business_task_id" not in columns:
                logger.info("开始添加 business_task_id 字段")

                await conn.execute(
                    text(
                        """
                        ALTER TABLE workflow_runs
                        ADD COLUMN business_task_id INTEGER
                        """
                    )
                )

                logger.info("business_task_id 字段添加成功")
            else:
                logger.info("business_task_id 字段已存在，跳过")

            # 5. 检查外键是否存在
            foreign_keys = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_foreign_keys(
                    "workflow_runs"
                )
            )

            fk_exists = any(
                fk.get("name") == "fk_workflow_runs_business_task"
                for fk in foreign_keys
            )

            if not fk_exists:
                await conn.execute(
                    text(
                        """
                        ALTER TABLE workflow_runs
                        ADD CONSTRAINT fk_workflow_runs_business_task
                        FOREIGN KEY (business_task_id)
                        REFERENCES business_tasks (id)
                        ON DELETE SET NULL
                        """
                    )
                )

                logger.info("business_task_id 外键添加成功")
            else:
                logger.info("business_task_id 外键已存在，跳过")

            # 6. 检查索引是否存在
            indexes = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_indexes(
                    "workflow_runs"
                )
            )

            index_exists = any(
                index.get("name")
                == "ix_workflow_runs_business_task_id"
                for index in indexes
            )

            if not index_exists:
                await conn.execute(
                    text(
                        """
                        CREATE INDEX ix_workflow_runs_business_task_id
                        ON workflow_runs (business_task_id)
                        """
                    )
                )

                logger.info("business_task_id 索引创建成功")
            else:
                logger.info("business_task_id 索引已存在，跳过")

        logger.info("数据库结构更新完成")

    except Exception:
        logger.exception("数据库结构更新失败")
        raise

    finally:
        await database.close_db_engine()


if __name__ == "__main__":
    asyncio.run(update_database())
