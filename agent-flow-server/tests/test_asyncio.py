import asyncio
import time

# async def worker(name: str, n: int):
#     for i in range(n):
#         print(f"[{name}] 第 {i} 步开始, time={time.time():.2f}")
#         await asyncio.sleep(1)   # 关键：await 时让出 CPU
#         print(f"[{name}] 第 {i} 步结束, time={time.time():.2f}")
#
# async def main():
#     start = time.time()
#     # 两个协程"并发"跑
#     await asyncio.gather(
#         worker("A", 3),
#         worker("B", 3),
#     )
#     print(f"总耗时 {time.time() - start:.2f}s")
#
# asyncio.run(main())


import asyncio
import time

async def fake_redis_event(delay: float, value: str):
    """模拟从 Redis 读一条事件：要等 delay 秒才来"""
    await asyncio.sleep(delay)
    return value

async def main():
    # 模拟"预读一条事件"，8 秒后才来
    next_event_task = asyncio.create_task(fake_redis_event(8, "RUN_COMPLETED"))

    start = time.time()
    while True:
        done, pending = await asyncio.wait({next_event_task}, timeout=2)

        if not done:
            # 2 秒内没等到事件 → 发心跳
            print(f"[{time.time()-start:.1f}s] 收到超时，发心跳 : ping")
            continue

        # 事件来了
        event = next_event_task.result()
        print(f"[{time.time()-start:.1f}s] 收到事件: {event}")
        break

asyncio.run(main())