# ARTSPACE 1.2.0 · AI 图生图

双击素材图片进入大预览，点击右上角 **更多 ⋯ → AI 图生图**。
原图自动成为图 1，输入修改指令，例如“把图 1 改为冬日雪景，保留建筑结构”。
也可以从素材库或本地文件添加额外参考图，按图 1、图 2 的顺序在指令中引用。

## 配置服务

在编辑面板右上角“服务配置”，或主页“设置与备份 → AI 图生图”添加配置。
支持保存多项服务，模型 ID 由用户填写，请使用实际服务支持的图像编辑模型。

| 接口类型 | 基础地址示例 | 用途 |
| --- | --- | --- |
| GPT / OpenAI 图像接口 | https://api.openai.com/v1 | images/edits，图片表单上传 |
| Gemini 原生接口 | https://generativelanguage.googleapis.com/v1beta | models/{model}:generateContent |
| Chat 兼容图像中转 | 服务商提供的地址，通常以 /v1 结尾 | chat/completions，需模型支持返回图片 |
| RunningHub | https://www.runninghub.cn | 应用或工作流图生图 |

基础地址不需要附加最终接口路径。原生 Gemini 与兼容中转是不同的协议，按服务商文档选择。
参考图数量上限需按实际模型能力配置；超出时会阻止提交，不会偷偷丢掉图片。
OpenAI 类型可填写服务支持的输出尺寸，留空则使用模型默认。

RunningHub 需要：API Key、应用/工作流 ID、提示词节点的 nodeId 与 fieldName、每张参考图对应的节点映射。
请从实际工作流或应用的 API 示例获取这些值，不能使用随机示例节点。
每次提供全部已配置参考图，第一版保留平台返回的第一个图片输出。

密钥使用 Windows DPAPI 加密保存。留空保存可保留原密钥，勾选清除可移除它。
这版没有内置密钥或余额；点击生成才会向已配置服务提交图片和指令。

## 结果与历史

- 生成过程中可以关闭面板，通过主页 **AI 任务** 再次打开。
- 生成完成后支持对比、下载、保存到素材库、继续修改。
- “继续修改”将结果作为新的图 1，输入下一轮指令即可。
- “保存到素材库”通过现有导入流程创建素材；在待整理中可找到，详情中保存提示词、平台及来源记录。
- 原图不会覆盖；相同内容沿用素材库去重规则。
- 每次保存不会重复导入。任务历史保留原始参考图快照。
- 文字修图由模型理解区域，不保证其他像素完全不变。

完成结果与任务记录存放在素材库的 `ai-edit` 目录，包含在完整备份内。
密钥换电脑或换 Windows 用户后需要重新填写。
关闭整个应用会中断本地等待；再次启动将明确显示“已中断”，不会自动发起新的付费请求。
RunningHub 平台任务 ID 会保留，超时或中断后可先到平台查询，避免重复提交。

## 验证范围

已用本地模拟服务验证四类协议的请求、响应、失败路径、入库与连续修改。
真实平台联调仍需要用户实际的地址、模型、密钥及 RunningHub 节点配置。
参考 st-chatu8 的修图交互思路，未复制其插件代码；没有加入无限画布或画笔蒙版。

接口参考：
- https://developers.openai.com/api/reference/resources/images/methods/edit
- https://ai.google.dev/gemini-api/docs/generate-content/image-generation
- https://www.runninghub.cn/runninghub-api-doc-cn/


## RunningHub 工作流

RunningHub 配置使用你自己的国际站账号、工作流或应用 ID、节点映射和 API Key。不同工作流的提示词节点、图片节点和输入要求不同，请按 RunningHub 提供的 API 示例填写；不要直接照抄其他用户的工作流 ID 或节点号。

API Key 只保存在本机素材库的 Windows 加密配置中，不包含在安装包里。
