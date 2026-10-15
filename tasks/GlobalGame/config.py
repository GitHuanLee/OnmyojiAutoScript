# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from tasks.GlobalGame.config_emergency import Emergency
from tasks.Component.config_base import ConfigBase
from tasks.Component.Costume.config import CostumeConfig

class Transport(str, Enum):
    TCP = 'TCP'
    SSL_TLS = 'SSL/TLS'


class GameAccountPlatform(str, Enum):
    """标识游戏账号登录渠道；枚举值会直接保存到实例配置文件中。"""

    IOS = 'IOS'
    ANDROID = 'Android'


class GameAccount(BaseModel):
    """保存一个游戏账号的登录凭据和客户端平台。"""

    account: str = Field(default='', title='Game Account', description='game_account_help')
    password: str = Field(default='', title='Game Password', description='game_password_help')
    platform: GameAccountPlatform = Field(default=GameAccountPlatform.ANDROID,
                                          title='Account Platform',
                                          description='game_account_platform_help')


class GameAccountSettings(BaseModel):
    """管理全局游戏账号列表，GUI 更新时校验列表条目并保留空白新增项。"""

    model_config = ConfigDict(validate_assignment=True)

    accounts: list[GameAccount] = Field(default_factory=lambda: [GameAccount()],
                                        title='Game Accounts',
                                        description='game_accounts_help')


class TeamFlow(BaseModel):
    enable: bool = Field(default=False, description='enable_help')
    broker: str = Field(default='', description='broker_help')
    port: int = Field(default=8883, description='port_help')
    transport: Transport = Field(default=Transport.TCP, description='transport_help')
    ca: str = Field(default='', description='ca_help')
    username: str = Field(default='', description='username_help')
    password: str = Field(default='', description='password_help')


class GlobalGame(BaseModel):
    """集中保存跨任务共享的游戏设置和账号凭据。"""

    emergency: Emergency = Field(default_factory=Emergency)
    costume_config: CostumeConfig = Field(default_factory=CostumeConfig)
    team_flow: TeamFlow = Field(default_factory=TeamFlow)
    account_settings: GameAccountSettings = Field(default_factory=GameAccountSettings,
                                                   title='Game Account Settings')

