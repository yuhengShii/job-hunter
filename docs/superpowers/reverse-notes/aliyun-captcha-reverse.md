# 阿里云验证码 v2 逆向笔记（51job 场景）

> 状态：**进行中**（2026-08-02 第一轮）。目标：脱离浏览器直接调用 verify 接口（K哥爬虫方案）。
> 来源：`https://we.51job.com/pc/search` 触发的 aliyunCaptcha（SLIDING 嵌入版，动态 JS 3.29.0 / sg 1.1.x）。

## 一、已确认的事实（实测/抓包）

### 1. 接口结构（域名与参数样本）

| 接口 | 域名 | Action | 关键参数 |
|---|---|---|---|
| 初始化 | `{prefix}.captcha-pro-open.aliyuncs.com/` | `InitCaptchaV2` | AaduaneId, UserUserId, UserId, UserCertifyId, DeviceData, SignatureNonce, Signature |
| 日志 | `upload.captcha-pro-open.aliyuncs.com/` | `UploadLog` | log(JSON), Signature |
| 设备1 | `device.captcha-open.aliyuncs.com` | `Log2` | Data(AES 密文), Signature |
| 设备2 | `device.captcha-open.aliyuncs.com` | `Log3` | Data(AES 密文), Signature |
| **验证** | `{prefix}-verify.captcha-pro-open.aliyuncs.com/` | `VerifyCaptchaV2` | SceneId, CertifyId, **CaptchaVerifyParam** |

- 51job 场景固定值：`AaduaneId=111jdk439dJJIjd023823201`、`SceneId=19x5u7lo`、`Version=2023-03-05`、`prefix=93bc86fc5f88a01515ccdf7ea6192e9f`（域名哈希前缀）
- 51job 调用链：queryPage 接口触发验证码 → 返回 `UserUserId/UserId/UserCertifyId` → 传给组件

### 2. CaptchaVerifyParam 结构（verify 请求体，URL 编码 JSON）

```json
{
  "sceneId": "19x5u7lo",
  "certifyId": "ac11000117856817375211159e00a4",
  "deviceToken": "V0VCI3NoODdi...<base64>",
  "data": "JRMnRw9REAU3...<base64 AES 密文>"
}
```

- `deviceToken`：Base64，明文前缀 `WEB#8h87bd1512hsb03cb405803a307dbe32-h-<timestamp>-<uuid>#`，后接 AES 密文
- `data`：轨迹数据的 AES 密文（key 链在 sg.js 内，Deflate 压缩 → Base64 → AES）

### 3. 验证结果码（服务端权威）

- `T001` = 通过；`F001/F002` = 失败。HTTP 200 + `Result.VerifyResult: false`（失败）
- 实测：CDP 模拟拖动（4 代轨迹 × headless/headful × stealth）全部 F001——**服务端强校验轨迹签名**

### 4. 签名算法（AliyunCaptcha.js `Ce`/`_e` 函数，已逆向）

```
Signature = base64(HMAC-SHA1(KEY_SECRET, M))
M = 参数按对象插入顺序拼接：encodeURIComponent(k)=encodeURIComponent(v)，& 连接
KEY_SECRET 带 "&" 后缀（K哥博客样例：YSKfst7GaVkXwZYvVihJsKF9r89koz&，本项目值未解出）
```

- `Ce(t, r)`：控制流扁平化状态机。`t`=参数对象，`r`=KEY_SECRET。case9 遍历参数（for...in 插入序），case2 拼接，case5 `return _e(处理过的key, M)`
- `_e(t, r) = ae[212+"y"](te()[195](r, t))`：te()[195]=HMAC-SHA1 构造，ae[212+"y"]=base64
- 参数对象构造（`je` 函数）：`AaduaneId` → `SignatureMethod` → `SignatureVersion` → `Format` → `Timestamp(hr())` → `Version` → `Action` → 合并业务参数 → `SignatureNonce(dr()=UUID)` → 签

### 5. 组件结构（AliyunCaptcha.js，IIFE + webpack 模块表）

- `window.AliyunCaptcha`：构造器（空壳），原型只有生命周期方法（init/bindEvents/show/hide/refresh/onBizSuccess/onBizFail/destroyCaptcha/startPOWCalculation/...）
- `AliyunCaptcha.prototype.onBizSuccess(t)`：验证通过回调——`btoa(JSON.stringify({certifyId, sceneId, isSign:!0, securityToken}))` 传给 51job 的 success 回调
- `this.captcha = new e3({...})`：e3 = Sliding 构造器（**核心逻辑闭包**，轨迹收集/加密/verify 都在内）
- 轨迹收集器（运行时 hook 到，mousedown/up 监听器）：拼接 `{事件类型}{0|1}+clientX+clientY+时间差` 到轨迹字符串，混淆字典 `Tm/WV/jy` 映射属性名
- sg.js（dynamicJS/3.29.0/sg.xxx.js）：运行时动态注入，**版本随机**（已见 066/069/075/077/099 五版），webpack 混淆，轨迹加密/deviceToken 生成在此
- FeiLin（行为采集 578KB）：页面级鼠标行为统计；AliyunCaptcha 在 ACTION_STATE.FAIL 时调 `window.FEILIN.initFeiLin`

## 二、未突破的封锁点

1. **KEY_SECRET 值**：`ke.KEY_SECRET = ge(pt, ht[re(218)])`，字符串表混淆（`re=ne`、`G(数字)` 索引）；btoa/atob/encodeURIComponent 全局 hook 均未命中签名路径（模块内实现）
2. **deviceToken/data 加密 key 链**：sg.js 闭包内，动态版本
3. **轨迹格式**（TrackList 等价物）与伪造数据生成

## 三、下一步路径（按性价比）

1. **静态解字符串表**：定位 `ne`/`G` 定义 + 字符串数组 → 解码 `re(218)` 与 KEY_SECRET 值 → 本地 Python 复现 InitCaptchaV2 签名 → 验证 DeviceConfig 获取（**里程碑 1**）
2. **sg.js 补环境**（Node v24 可用）：webpack bundle + DOM stub → 导出加密函数 → 生成 deviceToken/data（**里程碑 2**）
3. **轨迹伪造 + verify**：本地生成拟人轨迹（TrackList 格式）→ 加密 → POST verify → T001（**里程碑 3**）
4. **51job 集成**：T001 后拿 certifyId → 51job 数据接口（queryPage 带验证凭证）或页面内触发 onBizSuccess 回调

## 四、工具与资产

- 探针脚本（临时目录 `C:\Users\syh\AppData\Local\Temp\opencode\`）：probe_captcha（触发+基础拖动）、probe_solve（轨迹变体实验）、probe_diag2-5（状态诊断）、probe_fp（指纹对比）、probe_js（JS 抓取）、probe_dump/inst/src（组件 dump）、probe_params（请求参数样本）、probe_key/b64（CDP 断点）
- 抓取资产：`captcha_js\`（AliyunCaptcha.js 224KB、sg_*.js 五版、feilin124.js 578KB、main.css）
- 参数样本：`cap_params.json`（Init/UploadLog/Log2/Log3/Verify 全量）

## 五、结论（工程判断）

- 纯 UI 模拟拖动（CDP 事件）：**已穷尽**（0% 通过率，服务端 F001）
- 页面内 hook 轨迹/加密：**闭包保护不可行**（实例、加密函数均不可达）
- 完整接口逆向：**可行但有教程背书、数天级工作量**（K哥爬虫《某里 v2 滑动验证码分析》路线）
- 兜底方案（已验证有效）：检测 → 冷却 90s → 重试（实测风控滚动窗口自行解除，23 页后恢复）；headful 人工拖动 100% 可行
