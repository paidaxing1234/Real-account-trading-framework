"""
事件驱动引擎核心模块
参考 HftBacktest 框架设计，适配实盘交易场景
"""

from abc import ABC, abstractmethod
from typing import Callable, Type, Optional
from collections import deque
from itertools import chain
import copy
import time


class Event:
    """
    事件基类
    
    所有事件都包含：
    1. timestamp: 事件发生时间戳（毫秒）
    2. source: 事件来源（事件引擎ID）
    3. producer: 事件产生者（监听器函数）
    
    事件类型通过继承来实现，如 Order(Event), Data(Event)
    """
    
    __slots__ = ("timestamp", "source", "producer")
    
    def __init__(
        self,
        timestamp: Optional[int] = None,
        source: Optional[int] = None,
        producer: Optional[Callable] = None,
    ):
        self.timestamp = timestamp  # Unix时间戳（毫秒）
        self.source = source        # 事件引擎ID
        self.producer = producer    # 产生该事件的监听器
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(timestamp={self.timestamp}, source={self.source})"
    
    def copy(self) -> "Event":
        """浅拷贝事件"""
        return copy.copy(self)
    
    def derive(self) -> "Event":
        """
        派生新事件
        
        创建一个新事件副本，清空时间戳、来源、产生者
        用于在监听器中修改事件后重新推送
        """
        new_event = self.copy()
        new_event.timestamp = None
        new_event.source = None
        new_event.producer = None
        return new_event


class EventEngine:
    """
    事件引擎 - 事件驱动架构的核心
    
    职责：
    1. 接收事件（put方法）
    2. 分发事件给注册的监听器
    3. 管理全局时间戳
    4. 支持动态接口注入
    
    特性：
    - 事件按顺序处理，保证一致性
    - 支持类型化监听（只监听特定事件类型）
    - 支持全局监听（监听所有事件）
    - 防止监听器响应自己产生的事件（ignore_self）
    """
    
    def __init__(self):
        # 当前引擎时间戳（毫秒）
        self.timestamp = int(time.time() * 1000)
        
        # 监听器字典：{事件类型: [(监听器函数, ignore_self标志), ...]}
        self.listener_dict: dict[Type[Event], list[tuple[Callable[[Event], None], bool]]] = {}
        
        # 全局监听器（监听所有事件）
        self.senior_global_listeners: list[tuple[Callable[[Event], None], bool]] = []  # 优先级高
        self.junior_global_listeners: list[tuple[Callable[[Event], None], bool]] = []  # 优先级低
        
        # 事件队列
        self._queue: deque[Event] = deque()
        
        # 派发状态标志
        self._dispatching: bool = False
        
        # 当前正在执行的监听器
        self._current_listener: Optional[Callable[[Event], None]] = None
        
        # 引擎唯一ID（用于标识事件来源）
        self._id: int = id(self)
    
    def register(
        self,
        event_type: Type[Event],
        listener: Callable[[Event], None],
        ignore_self: bool = True,
    ):
        """
        注册事件监听器
        
        Args:
            event_type: 要监听的事件类型（Event的子类）
            listener: 监听器函数，签名为 (event: Event) -> None
            ignore_self: 是否忽略自己产生的事件（防止死循环）
        
        Example:
            engine.register(Order, strategy.on_order)
            engine.register(Data, strategy.on_data, ignore_self=False)
        """
        assert issubclass(event_type, Event), f"{event_type} must be subclass of Event"
        assert not self._dispatching, "Cannot register while dispatching events"
        
        # 初始化监听器列表
        if event_type not in self.listener_dict:
            self.listener_dict[event_type] = []
        
        lst = self.listener_dict[event_type]
        
        # 防止重复注册
        if listener in [l[0] for l in lst]:
            raise ValueError(f"Listener {listener} already registered for {event_type}")
        
        lst.append((listener, ignore_self))
    
    def global_register(
        self,
        listener: Callable[[Event], None],
        ignore_self: bool = False,
        is_senior: bool = False,
    ):
        """
        注册全局监听器（监听所有事件类型）
        
        Args:
            listener: 监听器函数
            ignore_self: 是否忽略自己产生的事件
            is_senior: 是否为高优先级监听器（在类型监听器之前执行）
        
        Example:
            # 用于日志记录等全局功能
            engine.global_register(logger.log_all_events)
        """
        assert not self._dispatching, "Cannot register while dispatching events"
        
        if is_senior:
            lst = self.senior_global_listeners
        else:
            lst = self.junior_global_listeners
        
        # 防止重复注册
        if listener in [l[0] for l in lst]:
            raise ValueError(f"Global listener {listener} already registered")
        
        lst.append((listener, ignore_self))
    
    def put(self, event: Event):
        """
        推送事件到引擎
        
        事件推送后会：
        1. 标注来源引擎ID
        2. 标注/更新时间戳
        3. 标注产生者（当前监听器）
        4. 入队等待派发
        5. 如果不在派发中，立即派发
        
        Args:
            event: 要推送的事件
        
        Example:
            order = Order(...)
            engine.put(order)
        """
        assert isinstance(event, Event), f"Must be Event instance, got {type(event)}"
        
        # 标注来源引擎
        if event.source is None:
            event.source = self._id
        
        # 处理时间戳
        ts = event.timestamp
        if ts is None:
            # 事件没有时间戳，使用引擎当前时间
            event.timestamp = self.timestamp
        elif ts > self.timestamp:
            # 事件时间戳更新，推进引擎时间
            self.timestamp = ts
        
        # 标注产生者（当前正在执行的监听器，None表示外部产生）
        event.producer = self._current_listener
        
        # 入队
        self._queue.append(event)
        
        # 如果不在派发中，立即开始派发
        if not self._dispatching:
            self._drain()
    
    def _drain(self):
        """
        派发事件队列中的所有事件
        
        派发顺序：
        1. Senior全局监听器
        2. 类型特定监听器
        3. Junior全局监听器
        """
        self._dispatching = True
        
        event_queue = self._queue
        listener_dict = self.listener_dict
        
        while event_queue:
            event = event_queue.popleft()
            
            # 获取所有要执行的监听器
            senior_global_lst = self.senior_global_listeners
            junior_global_lst = self.junior_global_listeners
            lst_local = listener_dict.get(type(event), ())
            
            # 按优先级顺序执行：senior_global → local → junior_global
            for listener, ignore_self in chain(senior_global_lst, lst_local, junior_global_lst):
                # 如果设置了ignore_self，且事件是自己产生的，跳过
                if ignore_self and event.producer is listener:
                    continue
                
                # 设置当前监听器（用于标注新产生的事件）
                self._current_listener = listener
                
                # 执行监听器
                try:
                    listener(event)
                except Exception as e:
                    # 监听器异常不应中断事件派发
                    print(f"Error in listener {listener}: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    self._current_listener = None
        
        self._dispatching = False
    
    def update_timestamp(self, timestamp: int):
        """
        手动更新引擎时间戳
        
        Args:
            timestamp: 新的时间戳（毫秒）
        """
        if timestamp > self.timestamp:
            self.timestamp = timestamp


class Component(ABC):
    """
    组件抽象基类
    
    所有功能模块都应继承此类，实现标准的生命周期管理
    
    生命周期：
    1. __init__: 初始化配置参数
    2. start(engine): 启动组件，注册监听器
    3. stop(): 停止组件，清理资源
    
    Example:
        class MyStrategy(Component):
            def start(self, engine: EventEngine):
                self.engine = engine
                engine.register(Data, self.on_data)
            
            def on_data(self, data: Data):
                # 处理行情
                pass
            
            def stop(self):
                # 清理资源
                pass
    """
    
    @abstractmethod
    def start(self, engine: EventEngine):
        """
        启动组件
        
        在这里：
        - 保存引擎引用
        - 注册事件监听器
        - 初始化运行时资源
        
        Args:
            engine: 事件引擎实例
        """
        pass
    
    @abstractmethod
    def stop(self):
        """
        停止组件
        
        在这里：
        - 清理资源
        - 关闭连接
        - 保存状态
        """
        pass


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("EventEngine 测试")
    print("=" * 60)
    
    # 创建引擎
    engine = EventEngine()
    
    # 定义测试事件
    class TestEvent(Event):
        def __init__(self, message: str, **kwargs):
            super().__init__(**kwargs)
            self.message = message
        
        def __repr__(self):
            return f"TestEvent(message='{self.message}', timestamp={self.timestamp})"
    
    # 定义监听器
    def listener_a(event: TestEvent):
        print(f"[Listener A] 收到: {event}")
    
    def listener_b(event: TestEvent):
        print(f"[Listener B] 收到: {event}")
        # 在监听器中产生新事件
        if event.message != "recursive":
            new_event = TestEvent("recursive", timestamp=event.timestamp + 1)
            engine.put(new_event)
    
    def global_listener(event: Event):
        print(f"[Global Listener] 收到: {event}")
    
    # 注册监听器
    print("\n1. 注册监听器...")
    engine.register(TestEvent, listener_a)
    engine.register(TestEvent, listener_b)
    engine.global_register(global_listener, is_senior=True)
    
    # 推送事件
    print("\n2. 推送事件...")
    event1 = TestEvent("Hello", timestamp=1000)
    engine.put(event1)
    
    print("\n3. 再推送一个事件...")
    event2 = TestEvent("World", timestamp=2000)
    engine.put(event2)
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

