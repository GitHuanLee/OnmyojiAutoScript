from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler
from pydantic import Field


class JadeDetectionConfig(ConfigBase):
    """勾协探测与寮30的业务开关及专用队友配置。"""

    jade_detection_enable: bool = Field(default=True, title="勾协探测", description="检测配置允许的勾协并按账号记录")
    guild_30_enable: bool = Field(default=False, title="寮30", description="登录后运行觉醒副本任务，沿用觉醒副本配置")
    guild_30_friend_1: str = Field(default="", title="寮30邀请队友1名称", description="支持*匹配任意字符；匹配多名时邀请列表中的第一位")
    guild_30_friend_2: str = Field(default="", title="寮30邀请队友2名称", description="支持*匹配任意字符；匹配多名时邀请列表中的第一位")


class JadeDetection(ConfigBase):
    """按全局账号文件顺序切换账号并执行勾协探测、寮30的任务配置。"""

    scheduler: Scheduler = Field(default_factory=Scheduler)
    jade_detection_config: JadeDetectionConfig = Field(default_factory=JadeDetectionConfig)
