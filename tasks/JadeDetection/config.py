from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler
from pydantic import Field


class JadeDetection(ConfigBase):
    """按全局账号文件顺序切换账号并执行勾协探测的任务配置。"""

    scheduler: Scheduler = Field(default_factory=Scheduler)
