---
name: deploy_server_tools_and_flow
description: deploy服务器上的部署工具及流程要求
type: project
---

deploy server 上包含 `trigger`（用于触发部署）和 `status`（用于检查部署状态）两个工具。部署流程要求：在触发部署后需要等待用户的人工确认，确认后方可继续检查部署状态。
