from module.atom.click import RuleClick
from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.GameUi.game_ui import GameUi
from tasks.Restart.login import LoginHandler
from tasks.GlobalGame.config import GameAccount, GameAccountPlatform, GameAccountType
from tasks.JadeDetection.assets import JadeDetectionAssets
from tasks.WantedQuests.script_task import ScriptTask as WantedQuestsTask


class AccountWantedQuestsTask(WantedQuestsTask):
    """在勾协探测账号流程中运行悬赏任务，并由外层统一负责调度。"""

    def next_run(self) -> None:
        """阻止嵌套悬赏任务覆盖 JadeDetection 的下一次运行时间。

        悬赏任务在完成或无可执行任务时都会调用此钩子；该账号流程的调度由外层
        JadeDetection 统一设置，因此这里不单独安排 WantedQuests。
        """
        # 保留 WantedQuests 的任务执行逻辑，但让外层任务独占调度时间的写入。
        return None


class ScriptTask(GameUi, SwitchAccountAssets, JadeDetectionAssets):
    """小号日常的勾协探测任务。

    任务从当前配置的全局账号文件读取账号，按文件顺序完成“进入游戏页→用户中心→切换账号→账号列表→
    账号匹配→登录→登录处理”流程。账号选择只依赖当前客户端已保存的账号，密码字段不在此处落盘
    或输入；页面异常交给统一调度器处理，避免多个任务各自实现登录重试。
    """

    def run(self) -> None:
        """按账号文件顺序执行勾协探测并结束本次任务。

        业务步骤是读取账号集合、逐个打开切换账号页面、滚动 OCR 列表查找账号、选择登录平台，
        再调用统一的 `app_handle_login()` 等待进入庭院，并运行悬赏任务。找不到单个账号时记录日志
        并继续后续账号；账号文件错误或登录流程请求人工接管时直接向上层抛出异常。
        """
        accounts = self.config.load_game_accounts()
        for index, account in enumerate(accounts, start=1):
            logger.info("Jade detection account %s/%s: %s", index, len(accounts), account.account)
            if not self._switch_to_account(account):
                logger.warning("Account not found in client account list: %s", account.account)
                continue
            try:
                AccountWantedQuestsTask(config=self.config, device=self.device).run()
            except TaskEnd:
                logger.info("Wanted quests completed for account: %s", account.account)
        self.set_next_run(task="JadeDetection", success=True, finish=True)
        raise TaskEnd("JadeDetection")

    def _switch_to_account(self, account: GameAccount) -> bool:
        """执行单个账号的界面切换、账号匹配和登录。

        :param account: 当前账号配置；`account` 必填，`account_type` 决定 OCR 比对规则，`platform` 决定
                        苹果或安卓平台按钮。
        :return: 找到并点击目标账号后返回 True；账号列表滚动到底仍未匹配返回 False。
        :raises Exception: 登录处理失败或页面无法恢复时由统一调度器处理。
        """
        # 入口是进入游戏页，点击用户中心并确认切换账号资源出现。
        if not self.ui_click(self.C_SA_LOGIN_FORM_USER_CENTER, self.I_JD_SWITCH_ACCOUNT, interval=2, timeout=20):
            return False
        # 点击切换账号，确认账号选择页的图1下拉资源出现。
        if not self.ui_click(self.I_JD_SWITCH_ACCOUNT, self.I_JD_ACCOUNT_DROPDOWN, interval=2, timeout=20):
            return False

        if not self._select_account(account):
            return False

        # 账号选择完成后，登录按钮消失且平台选择按钮出现，避免网络延迟时提前点击。
        platform_button = self.I_JD_APPLE if account.platform == GameAccountPlatform.IOS else self.I_SA_LOGIN_FORM_ANDROID
        if not self.ui_click(self.I_JD_LOGIN, platform_button, interval=1.5, timeout=20):
            return False
        # 平台按钮点击后可能直接进入加载页，也可能先显示区服/进入游戏按钮；
        # 统一交给 LoginHandler 处理，避免依赖单一版本的“进入游戏”模板。
        self.appear_then_click(platform_button, interval=1.5)

        # app_handle_login 负责加载页、登录页弹窗、区服选择和进入庭院后的收取流程。
        LoginHandler(config=self.config, device=self.device).app_handle_login()
        return True

    def _select_account(self, account: GameAccount) -> bool:
        """在“常用”账号列表中按 OCR 匹配并点击目标账号。

        :param account: 当前待选择账号；邮箱支持按 @ 前缀匹配，手机号优先精确匹配客户端展示文本。
        :return: 找到账号并点击返回 True；列表到底仍未找到返回 False。
        """
        account_list = self.O_SA_ACCOUNT_ACCOUNT_LIST
        last_ocr: tuple[str, ...] = ()
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
                self.click(target, interval=1)
                return True

            # OCR 结果不再变化时说明已经到列表底部，避免无限上滑。
            if self.appear(self.I_JD_ACCOUNT_BOTTOM):
                return False
            if texts and texts == last_ocr:
                return False
            last_ocr = texts
            self.swipe(self.S_JD_ACCOUNT_LIST_UP, interval=1.5)
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
