# 投手智囊出价API

只读、确定性的出价测试带服务，不连接或修改广告账户。

## 接口

- `GET /healthz`
- `GET /openapi.json`
- `POST /bid-simulate`

## Render部署

1. 将本目录全部文件上传至一个独立的私有GitHub仓库；
2. 在Render创建Web Service并连接该仓库；
3. Runtime选择Docker；
4. 添加秘密环境变量`BID_SIM_API_KEY`；
5. Health Check Path填`/healthz`；
6. 部署成功后访问`https://Render地址/healthz`。

不得提交或公开真实API Key。
