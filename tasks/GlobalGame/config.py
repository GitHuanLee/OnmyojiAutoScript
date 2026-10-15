# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tasks.GlobalGame.config_emergency import Emergency
from tasks.Component.config_base import ConfigBase
from tasks.Component.Costume.config import CostumeConfig
from module.config.utils import read_file

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
    """保存账号文件地址，并按需读取外部账号凭据。"""

    model_config = ConfigDict(validate_assignment=True)

    account_file: str = Field(default='config/accounts.json', title='Account File',
                               description='account_file_help')

    def load_accounts(self, base_dir: Path | None = None) -> list[GameAccount]:
        """读取并校验外部账号文件，文件内容不得写回主配置。

        文件支持 JSON/YAML，根节点可以是账号数组，也可以是包含 ``accounts``
        数组的对象；路径以工作目录为基准，传入 base_dir 仅用于测试和嵌入式调用。
        :return: 按文件顺序排列的账号列表。
        :raises ValueError: 文件不存在、格式错误或账号字段校验失败。
        """
        path = Path(self.account_file)
        if not path.is_absolute():
            path = (base_dir or Path.cwd()) / path
        if not path.is_file():
            raise ValueError(f'Account file does not exist: {path}')
        try:
            raw = read_file(str(path))
            rows = raw.get('accounts', []) if isinstance(raw, dict) else raw
            if not isinstance(rows, list):
                raise ValueError('Account file root must be a list or an object with accounts')
            return [GameAccount.model_validate(row) for row in rows]
        except (OSError, ValueError, TypeError, ValidationError) as exc:
            raise ValueError(f'Invalid account file: {path}') from exc


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

