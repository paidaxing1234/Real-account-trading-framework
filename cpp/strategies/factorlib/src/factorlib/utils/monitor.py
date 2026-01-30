import os
from threading import Event, Thread
from typing import Tuple

__all__ = ["start_cpu_monitor"]

def start_cpu_monitor(interval: float = 60.0) -> Tuple[Event, Thread]:
    """
    启动一个后台 CPU 监控线程，按固定间隔打印 CPU 使用率（优先使用 psutil）。
    返回 (stop_event, thread)。当需要停止监控时，调用 stop_event.set()。
    """
    try:
        import psutil  # type: ignore
        has_psutil = True
    except Exception:
        psutil = None  # type: ignore
        has_psutil = False

    stop_event: Event = Event()

    def _cpu_monitor() -> None:
        if has_psutil and psutil is not None:
            try:
                psutil.cpu_percent(interval=0.1)  # 预热，避免首次 0
            except Exception:
                pass
        while not stop_event.wait(timeout=interval):
            if has_psutil and psutil is not None:
                try:
                    cpu = psutil.cpu_percent(interval=None)
                    print(f"[CPU] usage={cpu:.1f}%")
                except Exception:
                    print("[CPU] psutil error")
            else:
                try:
                    la1, la5, la15 = os.getloadavg()
                    print(f"[CPU] loadavg1={la1:.2f} loadavg5={la5:.2f} loadavg15={la15:.2f}")
                except Exception:
                    print("[CPU] monitor unavailable")

    th = Thread(target=_cpu_monitor, daemon=True)
    th.start()
    return stop_event, th
