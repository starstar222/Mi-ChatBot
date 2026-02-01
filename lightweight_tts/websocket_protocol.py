# WebSocket 协议相关常量和类

class WebsocketStreamingMode:
    NONE = 'none'
    IN = 'in'
    OUT = 'out'
    DUPLEX = 'duplex'

# 协议常量
ACTION_KEY = 'action'
EVENT_KEY = 'event'
HEADER = 'header'
TASK_ID = 'task_id'

class EventType:
    STARTED = 'task-started'
    GENERATED = 'result-generated'
    FINISHED = 'task-finished'
    FAILED = 'task-failed'

class ActionType:
    START = 'run-task'
    CONTINUE = 'continue-task'
    FINISHED = 'finish-task'
