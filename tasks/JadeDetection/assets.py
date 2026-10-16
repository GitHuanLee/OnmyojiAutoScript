from module.atom.image import RuleImage

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
    I_JD_COMMON = RuleImage(
        roi_front=(0, 0, 79, 38), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_common.png")
    I_JD_LOGIN = RuleImage(
        roi_front=(0, 0, 139, 61), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_login.png")
    I_JD_APPLE = RuleImage(
        roi_front=(0, 0, 100, 100), roi_back=(0, 0, 1280, 720),
        threshold=0.75, method="Template matching",
        file="./tasks/JadeDetection/res/jd_apple.png")
