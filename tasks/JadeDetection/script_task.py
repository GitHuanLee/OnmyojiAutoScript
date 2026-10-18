import json
import os
import re
import tempfile
from time import monotonic, sleep
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from module.atom.click import RuleClick
from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.Component.SwitchAccount.exit_game import ExitGame
from tasks.GameUi.game_ui import GameUi
from tasks.Restart.login import LoginHandler
from tasks.Restart.assets import RestartAssets
from tasks.GlobalGame.config import GameAccount, GameAccountPlatform, GameAccountType
from tasks.JadeDetection.assets import JadeDetectionAssets
from tasks.GameUi.page import page_login, page_main
from tasks.EvoZone.script_task import ScriptTask as EvoZoneTask
from tasks.WantedQuests.assets import WantedQuestsAssets
from tasks.WantedQuests.config import CooperationSelectMask, CooperationType


class JadeDetectionLoginHandler(LoginHandler):
    """适配嵌套登录流程的处理器。

    `BaseTask` 会根据处理器类所在任务目录校验 `running_task`。JadeDetection
    复用 Restart 的登录逻辑时必须通过当前任务目录下的子类实例化，才能避免
    将全局配置中的运行任务误判为 Restart。
    """


class AccountEvoZoneTask(EvoZoneTask):
    """在 JadeDetection 流程中复用觉醒副本逻辑，调度仍由外层任务管理。"""

    def invite_friends(self, config) -> None:
        """使用 JadeDetection 专属队友名称，同时保留 EvoZone 的人数和等待设置。

        :param config: EvoZone 原邀请配置；人数和邀请选项沿用该配置。
        :return: 无返回值；邀请失败仍由通用流程记录并处理。
        """
        jade_config = self.config.jade_detection.jade_detection_config
        jade_invite_config = config.model_copy(update={
            "friend_1": jade_config.guild_30_friend_1,
            "friend_2": jade_config.guild_30_friend_2,
        })
        super().invite_friends(jade_invite_config)

    def detect_select(self, name: str = None) -> bool:
        """在寮30好友列表中按配置名称做模糊匹配并选择首个候选。

        配置中的 `*` 表示任意长度字符；没有 `*` 时按名称包含关系匹配。
        找不到候选时交回原始精确匹配流程，沿用其失败日志和返回行为。

        :param name: 当前配置的队友名称，空值按原邀请逻辑判为未找到。
        :return: 选择好友后返回 True，未匹配时返回原流程结果。
        """
        if not name:
            return super().detect_select(name)

        self.screenshot()
        candidates = []
        for rule in (self.O_FRIEND_NAME_1, self.O_FRIEND_NAME_2):
            for result in rule.detect_and_ocr(self.device.image):
                text = result.ocr_text.strip()
                if self._matches_guild_30_friend_name(name, text):
                    # OCR 框坐标相对规则 ROI，取框中心点击角色卡片文字区域。
                    x = int((result.box[:, 0].min() + result.box[:, 0].max()) / 2 + rule.roi[0])
                    y = int((result.box[:, 1].min() + result.box[:, 1].max()) / 2 + rule.roi[1])
                    candidates.append((y, x, text, rule.name))

        if not candidates:
            return super().detect_select(name)

        y, x, matched_name, rule_name = min(candidates)
        logger.info("Guild 30 friend name %s matched %s", name, matched_name)
        self.device.click(x=x, y=y, control_name=f"{rule_name}_fuzzy_friend")
        # 选中标记位于当前好友列的右上角，不能使用 GeneralInvite 中固定的
        # (895, 373) ROI；在当前列的 OCR 区域内复用同一模板做动态匹配。
        for _ in range(3):
            sleep(0.3)
            self.screenshot()
            if self._guild_30_selected(rule_name):
                break
        return True

    def _guild_30_selected(self, rule_name: str) -> bool:
        """在当前好友列中识别角色卡片右上角的选中勾标记。

        :param rule_name: 被选中的 OCR 好友列规则名称。
        :return: 当前列出现选中标记时返回 True，否则返回 False。
        """
        rule = self.O_FRIEND_NAME_1 if rule_name == self.O_FRIEND_NAME_1.name else self.O_FRIEND_NAME_2
        previous_roi = self.I_SELECTED.roi_back
        try:
            # match_all 会临时使用传入区域；限制在当前好友列可避免误匹配其他控件。
            x, y, width, height = rule.roi
            selected_roi = (max(0, x - 20), max(0, y - 30), width + 60, height + 60)
            return bool(self.I_SELECTED.match_all(self.device.image, roi=selected_roi))
        finally:
            self.I_SELECTED.roi_back = previous_roi

    @staticmethod
    def _matches_guild_30_friend_name(configured_name: str, detected_name: str) -> bool:
        """判断 OCR 好友名是否符合寮30配置的包含或星号通配规则。

        :param configured_name: 寮30专属好友名配置。
        :param detected_name: 好友列表中的 OCR 文本。
        :return: 名称匹配时返回 True。
        """
        if "*" in configured_name:
            pattern = "^" + ".*".join(re.escape(part) for part in configured_name.split("*")) + "$"
            return re.match(pattern, detected_name) is not None
        return configured_name in detected_name

    def set_next_run(self, task: str, *args, **kwargs) -> None:
        """阻止嵌套觉醒任务覆盖 JadeDetection 的下一次运行时间。

        觉醒任务由 `JadeDetection` 按账号串行调用，账号循环的调度由外层
        JadeDetection 统一设置，因此这里不单独安排 EvoZone。
        """
        if task == "EvoZone":
            return None
        return super().set_next_run(task, *args, **kwargs)


class ScriptTask(GameUi, SwitchAccountAssets, JadeDetectionAssets, WantedQuestsAssets, RestartAssets):
    """小号日常的勾协探测任务。

    任务按全局账号文件顺序登录账号，根据 JadeDetection 开关探测协作任务并按账号覆盖记录，
    再按需运行复用 EvoZone 配置的寮30。账号选择只依赖客户端已保存账号，异常交给统一调度器。
    """

    def run(self) -> None:
        """按账号文件顺序执行勾协探测并结束本次任务。

        逐个切换并登录账号；勾协探测只识别满足全局悬赏协作类型配置的协作，记录后即结束探测，
        不邀请好友、不开始协作战斗。之后可按配置运行寮30；账号文件错误或人工接管异常向上抛出。
        """
        accounts = self.config.load_game_accounts()
        jade_config = self.config.jade_detection.jade_detection_config
        if jade_config.jade_detection_enable:
            self._clear_previous_cooperation_record()
        for index, account in enumerate(accounts, start=1):
            logger.info("Jade detection account %s/%s: %s", index, len(accounts), account.account)
            if index > 1:
                self._prepare_account_switch()
            if not self._switch_to_account(account):
                logger.warning("Account not found in client account list: %s", account.account)
                continue
            if jade_config.jade_detection_enable:
                self._detect_cooperation(account)
            if jade_config.guild_30_enable:
                try:
                    AccountEvoZoneTask(config=self.config, device=self.device).run()
                except TaskEnd:
                    logger.info("Guild 30 completed for account: %s", account.account)
        self.set_next_run(task="JadeDetection", success=True, finish=True)
        raise TaskEnd("JadeDetection")

    def _prepare_account_switch(self) -> None:
        """在处理下一个账号前恢复到账号切换页面。

        :return: 无返回值；成功后当前页面应显示账号切换列表。
        :raises Exception: 页面导航或设备操作无法恢复时交给任务调度器处理。
        """
        # 悬赏结束后通常停留在庭院；其他异常页面先通过统一导航回到庭院。
        current_page = self.get_current_page(fallback=True)
        if current_page == page_login:
            # 登录页的进入钩子默认创建 Restart 处理器，会触发嵌套任务名校验；
            # 这里显式使用当前任务的适配处理器完成登录。
            JadeDetectionLoginHandler(config=self.config, device=self.device).app_handle_login()
        elif current_page != page_main:
            self.goto_page(page_main)
        # ExitGame 按既有流程点击右上角头像、用户中心和切换账号按钮。
        ExitGame.exitGame(self)

    def _detect_cooperation(self, account: GameAccount) -> None:
        """检查当前账号的协作任务，只记录符合悬赏配置的勾协。

        :param account: 当前登录账号，用于在共享文件内区分账号记录。
        :return: 无返回值；无匹配任务时不写入该账号记录。
        """
        self.goto_page(page_main)
        try:
            if not self._open_wanted_quests():
                logger.info("Wanted quests page unavailable for account %s", account.account)
                return
            if not any(self.appear(button) for button in self._cooperation_buttons()):
                logger.info("No cooperation task for account %s", account.account)
                return

            configured_mask = CooperationSelectMask[
                self.config.wanted_quests.wanted_quests_config.cooperation_type.value
            ]
            for cooperation_type, button in self._cooperation_info():
                if cooperation_type != CooperationType.Jade or not (cooperation_type & configured_mask):
                    continue
                jade_kind = self._classify_jade(button)
                self._write_cooperation_record(account, cooperation_type, jade_kind)
                logger.info("Detected %s for account %s", jade_kind, account.account)
                break
        finally:
            # 记录与否不改变悬赏任务的结束路径；关闭当前悬赏页后统一回到庭院，
            # 让下一账号切换和后续寮30任务从稳定页面开始。
            self._finish_cooperation_detection()

    def _finish_cooperation_detection(self) -> None:
        """关闭悬赏探测页面并确认回到庭院。"""
        self.screenshot()
        if self.appear(self.I_UI_BACK_RED):
            self.ui_click_until_disappear(self.I_UI_BACK_RED, interval=1)
        self.goto_page(page_main)

    def _classify_jade(self, button) -> str:
        """打开一次勾协详情，区分普通勾协与现世勾协并关闭详情。

        :param button: 当前勾协卡片的邀请位规则，仅用于计算详情入口坐标。
        :return: ``普通勾协``、``现世勾协`` 或无法识别时的 ``未知勾协``。
        """
        x, y, width, height = button.roi_front
        # 原悬赏任务使用邀请位上方 40 像素作为详情入口；这里只点击一次，
        # 后续只截图识别，避免页面加载期间重复点击触发框架保护。
        self.device.click(
            x=x + width // 2,
            y=y - 40,
            control_name=f"{button.name}_detail",
        )
        result = "未知勾协"
        for _ in range(10):
            sleep(0.5)
            self.screenshot()
            if self.appear(WantedQuestsAssets.I_WQ_TRACE_ONE_REALWORLD):
                result = "现世勾协"
                break
            if (self.appear(WantedQuestsAssets.I_WQ_TRACE_ONE_ENABLE)
                    or self.appear(WantedQuestsAssets.I_WQ_TRACE_ONE_DISABLE)):
                result = "普通勾协"
                break

        # 仅在详情状态出现时执行关闭，避免误点击悬赏列表。
        if result != "未知勾协":
            self.ui_click_until_smt_disappear(
                WantedQuestsAssets.C_WQ_TRACE_ONE_CLOSE,
                stop=WantedQuestsAssets.I_WQ_TRACE_ONE_CHECK_OPENED,
                interval=1.5,
            )
        else:
            logger.warning("Unable to classify jade cooperation button: %s", button.name)
        return result

    def _open_wanted_quests(self) -> bool:
        """按只做协作任务的前置流程打开悬赏页面，不邀请或追踪好友。"""
        back_seen_at = None
        for _ in range(30):
            self.screenshot()
            if self.appear(WantedQuestsAssets.I_TRACE_ENABLE) or self.appear(WantedQuestsAssets.I_TRACE_DISABLE):
                return True
            if self.appear_then_click(WantedQuestsAssets.I_WQ_SEAL, interval=1):
                continue
            if self.appear_then_click_multi_scale(
                WantedQuestsAssets.I_WQ_DONE, scale_range=(0.8, 1.2), interval=1
            ):
                back_seen_at = None
                continue
            if self.appear(self.I_UI_BACK_RED):
                # 悬赏页面刚打开时可能需要数秒加载 OCR/图片资源；原任务会持续等待，
                # 不能因一次未识别到追踪按钮就立即返回庭院，否则会漏掉当前账号的任务。
                if back_seen_at is None:
                    back_seen_at = monotonic()
                if monotonic() - back_seen_at >= 5:
                    self.ui_click_until_disappear(self.I_UI_BACK_RED)
                    return False
            else:
                back_seen_at = None
        return False

    @staticmethod
    def _cooperation_buttons():
        """返回悬赏界面三个固定协作邀请位置。"""
        return (WantedQuestsAssets.I_WQ_INVITE_1, WantedQuestsAssets.I_WQ_INVITE_2,
                WantedQuestsAssets.I_WQ_INVITE_3)

    def _cooperation_info(self) -> list[tuple[CooperationType, object]]:
        """识别悬赏界面各邀请位对应的协作类型及现世/普通勾协标识。

        :return: 按界面从左到右排列的 `(类型, 邀请按钮)` 列表。
        """
        detected = []
        type_rules = (
            ("JADE", CooperationType.Jade),
            ("DOG_FOOD", CooperationType.Food),
            ("CAT_FOOD", CooperationType.Food),
            ("SUSHI", CooperationType.Sushi),
            ("GOLD", CooperationType.Gold),
        )
        for index, button in enumerate(self._cooperation_buttons(), start=1):
            self.screenshot()
            if not self.appear(button):
                break
            for rule_name, cooperation_type in type_rules:
                rule = getattr(WantedQuestsAssets, f"I_WQ_COOPERATION_TYPE_{rule_name}_{index}")
                if self.appear(rule):
                    detected.append((cooperation_type, button))
                    break
        return detected

    def _write_cooperation_record(self, account: GameAccount, cooperation_type: CooperationType,
                                  jade_kind: str) -> None:
        """在共享记录中更新当前实例、当前账号的数据并原子写回。"""
        self._update_shared_records(
            lambda instance_records: instance_records.update({
                account.account: {
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "cooperation_type": cooperation_type.name,
                    "jade_kind": jade_kind,
                    "account": account.account,
                }
            })
        )

    @classmethod
    def _shared_record_path(cls) -> Path:
        """返回所有账号、配置实例共用的记录文件路径。"""
        return Path.cwd() / "account" / "jade_detection.json"

    def _instance_record_key(self) -> str:
        """返回共享文件内用于隔离并行 OAS 配置的实例键。"""
        return self.config.config_name

    def _clear_previous_cooperation_record(self) -> None:
        """清空当前实例上次的探测数据，同时保留其他并行实例记录。"""
        self._update_shared_records(lambda records: records.clear())

    def _update_shared_records(self, update) -> None:
        """通过进程锁读改写共享 JSON，并用同目录原子替换避免并行写损坏。

        每个实例只修改自己的命名空间；临时文件和目标文件位于同一目录，保证
        `os.replace` 在本地文件系统上为原子操作。
        """
        record_path = self._shared_record_path()
        record_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(record_path) + ".lock")
        with lock:
            if record_path.exists():
                with record_path.open("r", encoding="utf-8") as record_file:
                    records = json.load(record_file)
            else:
                records = {}
            if not isinstance(records, dict):
                raise ValueError(f"Invalid JadeDetection record format: {record_path}")

            instance_key = self._instance_record_key()
            instance_records = records.setdefault(instance_key, {})
            if not isinstance(instance_records, dict):
                raise ValueError(f"Invalid JadeDetection instance record: {instance_key}")
            update(instance_records)

            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=record_path.parent,
                    prefix=f"{record_path.name}.", suffix=".tmp", delete=False,
                ) as temporary_file:
                    temporary_path = Path(temporary_file.name)
                    json.dump(records, temporary_file, ensure_ascii=False, indent=2)
                    temporary_file.write("\n")
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                os.replace(temporary_path, record_path)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

    def _switch_to_account(self, account: GameAccount) -> bool:
        """执行单个账号的界面切换、账号匹配和登录。

        :param account: 当前账号配置；`account` 必填，`account_type` 决定 OCR 比对规则，`platform` 决定
                        苹果或安卓平台按钮。
        :return: 找到并点击目标账号后返回 True；账号列表滚动到底仍未匹配返回 False。
        :raises Exception: 登录处理失败或页面无法恢复时由统一调度器处理。
        """
        # ExitGame 完成后已经处于账号选择页，避免再次点击登录页用户中心。
        self.screenshot()
        account_page_ready = self.appear(self.I_SA_NETEASE_GAME_LOGO) and self.appear(self.I_SA_ACCOUNT_LOGIN_BTN)
        if not account_page_ready:
            # 入口仍在登录页时，先打开用户中心，再进入账号切换页。
            if not self.ui_click(self.C_SA_LOGIN_FORM_USER_CENTER, self.I_JD_SWITCH_ACCOUNT,
                                 interval=2, timeout=20):
                return False
            # 点击切换账号，确认账号选择页的下拉控件出现。
            if not self.ui_click(self.I_JD_SWITCH_ACCOUNT, self.I_JD_ACCOUNT_DROPDOWN,
                                 interval=2, timeout=20):
                return False

        if not self._select_account(account):
            return False

        # 账号选择完成后，登录按钮消失且平台选择按钮出现，避免网络延迟时提前点击。
        platform_button = self.I_JD_APPLE if account.platform == GameAccountPlatform.IOS else self.I_SA_LOGIN_FORM_ANDROID
        if not self.ui_click(self.I_JD_LOGIN, platform_button, interval=1.5, timeout=20):
            return False

        # 账号列表中的平台按钮必须先被点击，之后才允许交给登录处理器；
        # 若点击动画或网络延迟导致列表仍在当前页面，重试平台按钮，避免
        # LoginHandler 在账号列表页面持续 OCR“进入游戏”按钮。
        if not self._wait_account_login_transition(platform_button):
            logger.warning("Account list did not leave login page for account %s", account.account)
            return False

        # app_handle_login 负责加载页、登录页弹窗、区服选择和进入庭院后的收取流程。
        JadeDetectionLoginHandler(config=self.config, device=self.device).app_handle_login()
        return True

    def _wait_account_login_transition(self, platform_button) -> bool:
        """确认账号列表已进入登录流程，必要时重试平台按钮。

        :param platform_button: 当前账号对应的 Android 或 iOS 平台按钮。
        :return: 识别到登录表单、区服选择或进入游戏状态时返回 True。
        """
        for _ in range(20):
            self.screenshot()
            # 先处理“选择登录平台”中间页：识别到当前配置的平台按钮后点击，
            # 下一轮再确认是否进入登录表单、区服选择或进入游戏页面。
            if self.appear(self.I_SA_LOGIN_FORM_APPLE) or self.appear(self.I_SA_LOGIN_FORM_ANDROID):
                if self.appear_then_click(platform_button, interval=1.5):
                    continue
                logger.warning("Login platform page detected but configured platform button not found")
                continue
            if (self.appear(self.I_LOGIN_8)
                    or self.appear(self.I_LOGIN_SPECIFIC_SERVE)
                    or self.appear(self.I_CHECK_LOGIN_FORM)):
                return True
            # 账号列表关闭后通常先显示平台选择页；必须在这里点击一次，
            # 否则会一直等待“进入游戏”按钮而停留在该页面。
            if self.appear_then_click(platform_button, interval=1.5):
                continue
            if self.appear(self.I_SA_ACCOUNT_LOGIN_BTN):
                self.appear_then_click(platform_button, interval=1.5)
                continue
        return False

    def _select_account(self, account: GameAccount) -> bool:
        """在“常用”账号列表中按 OCR 匹配并点击目标账号。

        :param account: 当前待选择账号；邮箱支持按 @ 前缀匹配，手机号优先精确匹配客户端展示文本。
        :return: 找到账号并点击返回 True；列表到底仍未找到返回 False。
        """
        account_list = self.O_SA_ACCOUNT_ACCOUNT_LIST
        for _ in range(30):
            self.screenshot()
            # 下拉菜单未展开时先打开；点击“常用”后通常已展开，此分支兼容动画尚未完成的界面。
            if self.appear(self.I_JD_ACCOUNT_DROPDOWN):
                self.appear_then_click(self.I_JD_ACCOUNT_DROPDOWN, interval=1)
                continue

            results = account_list.detect_and_ocr(self.device.image)
            texts = tuple(result.ocr_text.strip() for result in results)
            for result, text in zip(results, texts):
                if not self._account_matches(account, text):
                    continue
                # OCR 返回框是相对 ROI 的坐标，必须换算回屏幕坐标后再点击账号行。
                box = result.box
                target = RuleClick(
                    roi_front=(
                        account_list.roi[0] + box[0][0],
                        account_list.roi[1] + box[0][1],
                        box[1][0] - box[0][0],
                        box[2][1] - box[1][1],
                    ),
                    roi_back=tuple(account_list.roi),
                    name="jd_account_row",
                )
                # 网易账号弹窗的首次点击可能只完成选中高亮，必须确认弹窗已关闭；
                # 否则后续平台按钮点击会落在账号列表上，登录处理器也会进入错误页面。
                for attempt in range(3):
                    self.click(target, interval=1)
                    for _ in range(8):
                        self.screenshot()
                        if self.appear(self.I_SA_ACCOUNT_LOGIN_BTN):
                            return True
                    if attempt < 2:
                        logger.warning("Account row click did not close account list, retry %s/2", attempt + 1)
                logger.warning("Account row selected but account list remains open: %s", account.account)
                return False

            # 只有识别到底部标志才结束；列表 OCR 暂时不变不能说明已经到底，
            # 因为本次小步滑动可能仍在动画中或只移动了一个行高。
            if self.appear(self.I_JD_ACCOUNT_BOTTOM):
                logger.warning("Account reached list bottom without finding: %s", account.account)
                return False
            self.swipe(self.S_JD_ACCOUNT_LIST_UP, interval=0)
            # 一次滑动完成后再 OCR，禁止连续发起滑动导致触发底部按钮误点击。
            sleep(1.0)
        return False

    @staticmethod
    def _account_matches(account: GameAccount, ocr_text: str) -> bool:
        """按照账号类型判断 OCR 文本是否对应配置账号。"""
        target = "".join(account.account.split())
        candidate = "".join(ocr_text.split())
        if not target or not candidate:
            return False
        if account.account_type == GameAccountType.EMAIL:
            # 邮箱中的 @ 经常被 OCR 误识别，前缀匹配与现有账号切换组件保持一致。
            return candidate == target or candidate.startswith(target.split("@", 1)[0])
        if candidate == target:
            return True
        # 手机号常被客户端显示为 153****4444；用末四位和数字前缀确认同一账号。
        if account.account_type == GameAccountType.PHONE:
            digits = ''.join(char for char in target if char.isdigit())
            candidate_digits = ''.join(char for char in candidate if char.isdigit())
            return len(digits) >= 4 and candidate_digits.endswith(digits[-4:]) and (
                candidate.startswith(digits[:3]) or digits[:3] in candidate)
        return False


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    ScriptTask(Config("oas1"), Device(Config("oas1"))).run()
