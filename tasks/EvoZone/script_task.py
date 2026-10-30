# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import time, datetime, timedelta

import numpy as np

from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralBuff.general_buff import GeneralBuff
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_awake_zones, page_shikigami_records
from tasks.EvoZone.assets import EvoZoneAssets
from tasks.EvoZone.config import EvoZone, UserStatus, KirinType
from tasks.Component.GeneralBattle.battle_wait import battle_wait_strategy

from module.logger import logger
from module.exception import TaskEnd


class ScriptTask(GeneralBattle, GeneralInvite, GeneralBuff, GeneralRoom, GameUi, EvoZoneAssets, SwitchSoul):

    def battle_before(self, buff, config, timeout: float = 5) -> bool:
        """首次战斗进入通用准备流程前先完成协战式神配置。"""
        if self.current_count == 1 and not getattr(self, '_coop_shikigami_checked', False):
            self._battle_before_team_ready()
        return super().battle_before(buff, config, timeout)

    def _battle_before_team_ready(self) -> None:
        """首次觉醒战斗前自动上阵首张协战式神。

        业务规则：进入首次觉醒准备界面后，打开式神配置；首张卡片显示 ``x/15``
        表示协战式神。若卡片顶部没有出战标志，则拖动到屏幕中心完成上阵。
        后续准备和战斗仍交由通用战斗流程处理。识别不到配置界面时在有限等待后
        回到既有准备流程，避免因资源加载或分辨率差异阻塞任务。

        该钩子在通用流程切换预设阵容后调用，保证协战式神不会被预设覆盖。
        """
        if getattr(self, '_coop_shikigami_checked', False):
            return
        self._coop_shikigami_checked = True
        if self.current_count == 1:
            self._prepare_first_coop_shikigami()

    @staticmethod
    def _has_deployed_mark(image: np.ndarray, roi: tuple[int, int, int, int] = (250, 480, 120, 48)) -> bool:
        """检测首张式神卡片顶部的白色 X 出战标志。

        标志是固定卡片布局中的浅色交叉线。使用低饱和高亮像素的两条窄对角带，
        比整块模板匹配更能适应卡片头像和特效变化，也不依赖外部二进制资源。
        """
        if image is None or image.ndim != 3:
            return False
        x, y, width, height = roi
        crop = image[y:y + height, x:x + width]
        if crop.shape[0] < height or crop.shape[1] < width:
            return False
        neutral = (crop.max(axis=2) - crop.min(axis=2) < 55) & (crop.mean(axis=2) > 165)
        # 出战 X 位于首张卡片左上方，而不是卡片几何中心。
        center_x, center_y = 30, 22
        grid_y, grid_x = np.indices((height, width))
        diagonal_a = np.abs((grid_y - center_y) - (grid_x - center_x)) <= 3
        diagonal_b = np.abs((grid_y - center_y) + (grid_x - center_x)) <= 3
        return int(np.count_nonzero(neutral & diagonal_a)) >= 8 and int(
            np.count_nonzero(neutral & diagonal_b)) >= 8

    def _prepare_first_coop_shikigami(self) -> None:
        """识别并拖动首张协战式神，最多等待有限时间后返回主流程。"""
        deadline = datetime.now() + timedelta(seconds=5)
        click_points = ((400, 470), (260, 520), (600, 520))
        click_index = 0
        next_click = datetime.min
        while datetime.now() < deadline:
            self.screenshot()
            count = self.O_COOP_SHIKIGAMI_COUNT.ocr(self.device.image)
            if not isinstance(count, tuple) or count[2] != 15:
                # 队员与队长的角色站位不同，固定点击红框内多个稳定点，避免随机点落在不可点击对象上。
                if datetime.now() >= next_click:
                    x, y = click_points[click_index % len(click_points)]
                    self.device.click(x=x, y=y, control_name='SHIKIGAMI_AREA')
                    click_index += 1
                    next_click = datetime.now() + timedelta(milliseconds=700)
                sleep(0.2)
                continue
            if self._has_deployed_mark(self.device.image):
                return
            # 卡片中心拖到屏幕中心，触发游戏的上阵判定。
            self.device.drag(self.C_COOP_SHIKIGAMI_CARD.center, (640, 360), name='COOP_SHIKIGAMI_DRAG')
            verify_deadline = datetime.now() + timedelta(seconds=2)
            while datetime.now() < verify_deadline:
                self.screenshot()
                if self._has_deployed_mark(self.device.image):
                    return
                sleep(0.2)
            logger.warning('协战式神拖动后未检测到出战标志，继续准备流程')
            return

    def run(self) -> bool:

        limit_count = self.config.evo_zone.evo_zone_config.limit_count
        limit_time = self.config.evo_zone.evo_zone_config.limit_time
        self.current_count = 0
        self.limit_count: int = limit_count
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute,
                                               seconds=limit_time.second)
        con = self.config.evo_zone
        if con.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
        if con.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)

        self.goto_page(page_main)
        config: EvoZone = self.config.evo_zone
        if config.evo_zone_config.soul_buff_enable:
            self.open_buff()
            self.awake(is_open=True)
            self.close_buff()

        success = True
        match config.evo_zone_config.user_status:
            case UserStatus.LEADER:
                success = self.run_leader()
            case UserStatus.MEMBER:
                success = self.run_member()
            case UserStatus.ALONE:
                self.run_alone()
            case UserStatus.WILD:
                self.run_wild()
            case _:
                logger.error('Unknown user status')

        # 记得关掉
        if config.evo_zone_config.soul_buff_enable:
            self.open_buff()
            self.awake(is_open=False)
            self.close_buff()
        # 下一次运行时间
        if success:
            self.set_next_run('EvoZone', finish=True, success=True)
        else:
            self.set_next_run('EvoZone', finish=False, success=False)

        raise TaskEnd

    def evozone_enter(self) -> bool:
        logger.info('Enter evozone')
        kirintype = self.I_LIGHTNING_KIRIN
        match self.config.evo_zone.evo_zone_config.kirin_type:
            case KirinType.FIREKIRIN:
                kirintype = self.I_FIRE_KIRIN
            case KirinType.WINDKIRIN:
                kirintype = self.I_WIND_KIRIN
            case KirinType.WATERKIRIN:
                kirintype = self.I_WATER_KIRIN
            case KirinType.LIGHTNINGKIRIN:
                kirintype = self.I_LIGHTNING_KIRIN
        while True:
            self.screenshot()
            if self.appear(self.I_FORM_TEAM):
                return True
            if self.appear_then_click(kirintype, interval=1):
                continue

    def check_layer(self, layer: str) -> bool:
        """
        检查挑战的层数, 并选中挑战的层
        :return:
        """
        pos = self.list_find(self.L_LAYER_LIST, layer)
        if pos:
            self.device.click(x=pos[0], y=pos[1])
            return True

    def check_lock(self, lock: bool = True) -> bool:
        """
        检查是否锁定阵容, 要求在觉醒界面
        :param lock:
        :return:
        """
        logger.info('Check lock: %s', lock)
        if lock:
            while 1:
                self.screenshot()
                if self.appear(self.I_EVOZONE_LOCK):
                    return True
                if self.appear_then_click(self.I_EVOZONE_UNLOCK, interval=1):
                    continue
        else:
            while 1:
                self.screenshot()
                if self.appear(self.I_EVOZONE_UNLOCK):
                    return True
                if self.appear_then_click(self.I_EVOZONE_LOCK, interval=1):
                    continue

    def run_leader(self):
        logger.info('Start run leader')
        # self.ui_goto(page_soul_zones)
        self.goto_page(page_awake_zones)
        self.evozone_enter()
        layer = self.config.evo_zone.evo_zone_config.layer
        logger.info("test0")
        self.check_layer(layer)
        logger.info("test1")
        self.check_lock(self.config.evo_zone.general_battle_config.lock_team_enable)
        logger.info("test2")
        # 创建队伍
        logger.info('Create team')
        while 1:
            self.screenshot()
            # 部分账号的队伍页头像状态不同或未解锁；右下角创建队伍按钮才是稳定入口。
            if self.appear(self.I_CREATE_ROOM):
                break
            if self.appear_then_click(self.I_FORM_TEAM, interval=1):
                continue
        # 创建房间
        self.create_room()
        self.ensure_private()
        self.create_ensure()

        # 邀请队友
        success = True
        is_first = True
        # 这个时候我已经进入房间了哦
        while 1:
            self.screenshot()
            # 无论胜利与否, 都会出现是否邀请一次队友
            # 区别在于，失败的话不会出现那个勾选默认邀请的框
            if self.check_and_invite(self.config.evo_zone.invite_config.default_invite):
                continue

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_WIN_3, interval=1):
                continue

            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('EvoZone count limit out')
                    break

            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('EvoZone time limit out')
                    break

            # 如果没有进入房间那就不需要后面的邀请
            if not self.is_in_room():
                # 如果在探索界面或者是出现在组队界面， 那就是可能房间死了
                # 要结束任务
                sleep(0.5)
                if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                    sleep(0.5)
                    if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                        logger.warning('EvoZone task failed')
                        success = False
                        break
                continue

            # 点击挑战
            if not is_first:
                if self.run_invite(config=self.config.evo_zone.invite_config):
                    self.run_general_battle(config=self.config.evo_zone.general_battle_config)
                else:
                    # 邀请失败，退出任务
                    logger.warning('Invite failed and exit this EvoZone task')
                    success = False
                    break

            # 第一次会邀请队友
            if is_first:
                if not self.run_invite(config=self.config.evo_zone.invite_config, is_first=True):
                    logger.warning('Invite failed and exit this evozone task')
                    success = False
                    break
                else:
                    is_first = False
                    self.run_general_battle(config=self.config.evo_zone.general_battle_config)

        # 当结束或者是失败退出循环的时候只有两个UI的可能，在房间或者是在组队界面
        # 如果在房间就退出
        if self.exit_room():
            pass
        # 如果在组队界面就退出
        if self.exit_team():
            pass

        self.goto_page(page_main)

        if not success:
            return False
        return True

    def run_member(self):
        logger.info('Start run member')
        # self.ui_goto(page_soul_zones)
        # self.evozone_enter()
        # self.check_lock(self.config.evo_zone.general_battle_config.lock_team_enable)

        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_WIN_3, interval=1):
                continue

            if self.current_count >= self.limit_count:
                logger.info('EvoZone count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('EvoZone time limit out')
                break

            if self.check_then_accept():
                continue

            if self.is_in_room():
                self.device.stuck_record_clear()
                if self.wait_battle(wait_time=self.config.evo_zone.invite_config.wait_time):
                    self.run_general_battle(config=self.config.evo_zone.general_battle_config)
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            elif self.check_take_over_battle(False, config=self.config.evo_zone.general_battle_config):
                continue

        while 1:
            # 有一种情况是本来要退出的，但是队长邀请了进入的战斗的加载界面
            if self.appear(self.I_GI_HOME) or self.appear(self.I_GI_EXPLORE):
                break
            # 如果可能在房间就退出
            if self.exit_room():
                pass
            # 如果还在战斗中，就退出战斗
            if self.exit_battle():
                pass

        self.goto_page(page_main)
        return True

    def run_alone(self):
        logger.info('Start run alone')
        self.goto_page(page_awake_zones)
        self.evozone_enter()
        layer = self.config.evo_zone.evo_zone_config.layer
        self.check_layer(layer)
        self.check_lock(self.config.evo_zone.general_battle_config.lock_team_enable)

        def is_in_evozone(screenshot=False) -> bool:
            if screenshot:
                self.screenshot()
            return self.appear(self.I_EVOZONE_FIRE)

        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_WIN_3, interval=1):
                continue

            if not is_in_evozone():
                continue

            if self.current_count >= self.limit_count:
                logger.info('EvoZone count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('EvoZone time limit out')
                break

            # 点击挑战
            while 1:
                self.screenshot()
                if self.appear_then_click(self.I_EVOZONE_FIRE, interval=1):
                    pass

                if not self.appear(self.I_EVOZONE_FIRE):
                    self.run_general_battle(config=self.config.evo_zone.general_battle_config)
                    break

        # 回去
        while 1:
            self.screenshot()
            if not self.appear(self.I_FORM_TEAM):
                break
            if self.appear_then_click(self.I_BACK_Y, interval=1):
                continue

        self.goto_page(page_main)

    def run_wild(self):
        logger.error('Wild mode is not implemented')
        pass


    @battle_wait_strategy()
    def battle_wait(self, *args, **kwargs):
        return self.battle_wait_with_strategy(*args, **kwargs)



if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()

    # t.check_layer('悲')

    from module.base.timer import timer
