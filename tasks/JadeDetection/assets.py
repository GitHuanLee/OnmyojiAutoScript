from module.atom.image import RuleImage
from module.atom.swipe import RuleSwipe

# This Python file mirrors the rules declared in res/image.json.
# The JSON file remains the source of truth for future asset regeneration.
class JadeDetectionAssets:
    """勾协探测任务的页面模板资源。"""

    I_JD_USER_CENTER = RuleImage(
        roi_front=(0, 0, 81, 60), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_user_center.png")
    I_JD_SWITCH_ACCOUNT = RuleImage(
        roi_front=(0, 0, 139, 61), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_switch_account.png")
    I_JD_ACCOUNT_DROPDOWN = RuleImage(
        roi_front=(0, 0, 66, 34), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_account_dropdown.png")
    I_JD_LOGIN = RuleImage(
        roi_front=(0, 0, 139, 61), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_login.png")
    I_JD_APPLE = RuleImage(
        roi_front=(0, 0, 100, 100), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_apple.png")
    I_JD_ACCOUNT_BOTTOM = RuleImage(
        roi_front=(0, 0, 124, 36), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_account_bottom.png")
    I_JD_ENTER_GAME = RuleImage(
        roi_front=(0, 0, 158, 44), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_enter_game.png")
    # 账号列表未找到目标时，从屏幕中央向上滑动继续扫描。
    S_JD_ACCOUNT_LIST_UP = RuleSwipe(
        # 账号行高度约 110~120 像素，每次只上移一行，避免一次滑过目标账号。
        roi_front=(640, 420, 1, 1), roi_back=(640, 300, 1, 1),
        mode="vector", name="jd_account_list_up")
