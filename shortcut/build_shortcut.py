#!/usr/bin/env python3
"""
生成 iOS 快捷指令 .shortcut 文件(未签名二进制 plist)。

设计(无 If 控制流,最大化导入成功率):
  分享菜单输入 / 手动粘贴 -> URL编码 -> 调 td.woyin.me/extract -> 取 video_url
  -> 下载 mp4 -> 存相册 -> 提示成功

注意:这是尽力生成(best-effort)。.shortcut 是二进制 plist,个别动作参数键
若与现代 iOS 期望略有出入,导入后该动作可能为空——届时请按 README 手搓指南补全。
导入前需在 设置 -> 快捷指令 打开「允许不受信任的快捷指令」。
"""
import plistlib
import uuid

FFFC = "\uFFFC"  # Object Replacement Character,变量占位


def u():
    return str(uuid.uuid4()).upper()


def tok_text(parts):
    """
    构造 WFTextTokenString:parts 是 [(literal_or_None, var_or_None), ...]
    其中 literal 为普通字符串片段,var 为 (变量名, kind) 或 action output 引用。
    简化:parts 为 list,元素为 str(字面量) 或 ('var', name) / ('out', outputName, outputUUID)。
    """
    s = ""
    ranges = {}
    for p in parts:
        if isinstance(p, tuple) and p[0] == "var":
            loc = len(s)
            s += FFFC
            ranges[f"{{{loc}, 1}}"] = {"VariableName": p[1], "Type": "Variable"}
        elif isinstance(p, tuple) and p[0] == "out":
            loc = len(s)
            s += FFFC
            ranges[f"{{{loc}, 1}}"] = {
                "OutputName": p[1], "OutputUUID": p[2], "Type": "ActionOutput",
            }
        else:
            s += p
    return {"Value": {"attachmentsByRange": ranges, "string": s},
            "WFSerializationType": "WFTextTokenString"}


def attach_var(name):
    return {"Value": {"VariableName": name, "Type": "Variable"},
            "WFSerializationType": "WFTextTokenAttachment"}


def attach_out(name, uid):
    return {"Value": {"OutputName": name, "OutputUUID": uid, "Type": "ActionOutput"},
            "WFSerializationType": "WFTextTokenAttachment"}


def action(ident, params, uid=None, out_name=None):
    p = {}
    if uid:
        p["UUID"] = uid
    if out_name:
        p["CustomOutputName"] = out_name
    p.update(params)
    return {"WFWorkflowActionIdentifier": ident, "WFWorkflowActionParameters": p}


# ---- 动作 UUID ----
U_KEYTXT, U_SETKEY = u(), u()
U_GETIN, U_ASK = u(), u()
U_ENC, U_APITXT = u(), u()
U_GETAPI, U_GETDICT_URL, U_GETDICT_MSG = u(), u(), u()
U_DL, U_SAVE, U_NOTIFY = u(), u(), u()

actions = []

# 0. Text:API Key(导入时由 ImportQuestion 填入;默认占位)
actions.append(action(
    "is.workflow.actions.gettext",
    {"WFTextActionText": "在此粘贴你的 API_KEY"},
    uid=U_KEYTXT, out_name="APIKey"))

# 1. Set Variable api_key
actions.append(action(
    "is.workflow.actions.setvariable",
    {"WFVariableName": "api_key", "WFInput": attach_out("APIKey", U_KEYTXT)},
    uid=U_SETKEY))

# 2. Get Variable:Shortcut Input(分享菜单传入的 URL)
actions.append(action(
    "is.workflow.actions.getvariable",
    {"WFVariable": attach_var("Shortcut Input")},
    uid=U_GETIN, out_name="InURL"))

# 3. Ask for Input:URL(默认填入分享菜单的 URL;手动运行时留空让你粘贴)
actions.append(action(
    "is.workflow.actions.ask",
    {"WFInputType": "URL",
     "WFAskActionPrompt": "粘贴 x.com / twitter.com 视频链接",
     "WFAskActionDefaultAnswer": attach_out("InURL", U_GETIN)},
    uid=U_ASK, out_name="TweetURL"))

# 4. URL Encode(把推文链接编码成合法 query value,避免 ?s=&t= 截断)
actions.append(action(
    "is.workflow.actions.urlencode",
    {"WFInput": attach_out("TweetURL", U_ASK), "WFEncodeType": "URL"},
    uid=U_ENC, out_name="TweetEnc"))

# 5. Text:拼接完整 extract URL(内嵌 TweetEnc 与 api_key 两个变量)
actions.append(action(
    "is.workflow.actions.gettext",
    {"WFTextActionText": tok_text([
        "https://td.woyin.me/extract?xid=",
        ("out", "TweetEnc", U_ENC),
        "&x-api-key=",
        ("out", "APIKey", U_KEYTXT),
    ])},
    uid=U_APITXT, out_name="APIURL"))

# 6. Get Contents of URL(GET 解析接口)
actions.append(action(
    "is.workflow.actions.getcontentsofurl",
    {"URL": attach_out("APIURL", U_APITXT)},
    uid=U_GETAPI, out_name="Resp"))

# 7. Get Dictionary Value:video_url
actions.append(action(
    "is.workflow.actions.getvaluefordictionarykey",
    {"WFInput": attach_out("Resp", U_GETAPI),
     "WFDictionaryKey": tok_text(["video_url"])},
    uid=U_GETDICT_URL, out_name="VideoURL"))

# 8. Get Dictionary Value:message(失败原因,供提示)
actions.append(action(
    "is.workflow.actions.getvaluefordictionarykey",
    {"WFInput": attach_out("Resp", U_GETAPI),
     "WFDictionaryKey": tok_text(["message"])},
    uid=U_GETDICT_MSG, out_name="Msg"))

# 9. Get Contents of URL:下载 mp4(VideoURL 为空时此步会报错——即“无视频”的反馈)
actions.append(action(
    "is.workflow.actions.getcontentsofurl",
    {"URL": attach_out("VideoURL", U_GETDICT_URL)},
    uid=U_DL, out_name="MP4"))

# 10. Save to Photo Album
actions.append(action(
    "is.workflow.actions.savetocameraroll",
    {"WFInput": attach_out("MP4", U_DL)},
    uid=U_SAVE))

# 11. Show Result:成功提示
actions.append(action(
    "is.workflow.actions.showresult",
    {"Text": tok_text(["✅ 视频已保存到相册"])},
    uid=U_NOTIFY))

shortcut = {
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowIcon": {
        "WFWorkflowIconStartColor": 463140863,   # Blue
        "WFWorkflowIconGlyphNumber": 59511,        # film/video glyph
    },
    "WFWorkflowImportQuestions": [
        {
            "ActionIndex": 0,
            "Category": "Parameter",
            "ParameterKey": "WFTextActionText",
            "Text": "请输入服务器的 API Key(x-api-key,与 docker-compose 的 API_KEY 一致):",
            "DefaultValue": "",
        }
    ],
    "WFWorkflowInputContentItemClasses": [
        "WFURLContentItem", "WFStringContentItem", "WFSafariWebPageContentItem",
    ],
    "WFWorkflowTypes": ["NCWidget", "ActionExtension"],
    "WFWorkflowActions": actions,
}

with open("X视频下载.shortcut", "wb") as f:
    plistlib.dump(shortcut, f, fmt=plistlib.FMT_BINARY)
print("✅ 已生成 X视频下载.shortcut,共", len(actions), "个动作")
