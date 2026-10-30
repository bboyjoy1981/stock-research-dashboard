# A股科技投资决策看板

这是一个用于市场研究、仓位纪律和交易复盘的本地网页工具，不自动下单、不自动交易。

## 本地启动

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8505
```

打开 http://localhost:8505。也可以直接右键使用 PowerShell 运行 `./run_local.ps1`。

第一版使用演示数据；可以先验证页面和个人决策流程，再接入合法、稳定的行情数据源。

## 腾讯云部署

建议使用轻量应用服务器，安装 Python 3.11，复制项目后运行 `bash run_server.sh`，再使用 systemd 或 supervisor 保持 Streamlit 运行，并由 Nginx 反向代理到 8505 端口。公网使用前应增加访问认证、HTTPS 和数据库备份。Windows 本机使用 `run_local.ps1`。
## 行情数据接入

当前版本支持三种模式：演示数据、从同花顺导出的 CSV/XLSX 文件，以及可选的 Tushare Pro 日线数据。网页不会保存密钥，也不会执行下单。

在本机或腾讯云服务器配置环境变量后重启应用：

```powershell
$env:TUSHARE_TOKEN = "你的Token"
python -m pip install tushare
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8505
```

Linux 服务器对应：`export TUSHARE_TOKEN="你的Token"`。配置成功后，侧边栏“数据源接入”会显示已配置。实时/分钟行情仍应使用有授权的终端或行情服务；同花顺数据建议继续通过导出文件导入，避免网页抓取和账号风险。

服务器配置模板在 deploy 目录：

- stock-dashboard.service：systemd 常驻服务模板，默认只监听本机 8505 端口。
- nginx.stock-dashboard.conf.example：Nginx 反向代理模板。正式公网使用前请替换域名并配置 HTTPS、访问认证和防火墙规则。

## 主题比较

公共研究区的“主题比较”支持先按 CPO/光通信/PCB、存储半导体、机器人/自动化、国产替代、消费电子等主题筛选，再选择最多 6 只股票进行横向比较。页面提供排序、涨跌幅图表、研究备注和 CSV 导出，适合收盘后做题材内部比较，不执行交易。

## 第四阶段使用流程

收盘后从同花顺导出全市场数据，在“数据导入”上传并检查行情覆盖率；进入“市场阶段”确认六项判断并保存快照；在“决策驾驶舱”查看仓位范围、市场摘要和集中度提醒；在“主题比较”完成题材内部对比；最后在“交易计划与复盘”记录计划、实际成交和复盘结果。数据库和导入文件可使用项目内备份脚本归档。

## 第五阶段运维

侧边栏会显示最近导入数据日期；数据超过 3 天未更新时会提示重新导入。部署到腾讯云时建议仅开放反向代理端口，限制 Streamlit 内部端口的公网访问，并使用 `backup_server.sh` 和 `deploy/backup.cron.example` 定期备份 `decision.db` 与 `data/imports`。报告可从决策驾驶舱、主题比较和交易计划与复盘页面分别导出 CSV。

## 第六阶段路线

第六阶段围绕数据层、报告中心和风险看板展开：行情统一接入、按日期查看历史报告、跟踪组合风险趋势，并为腾讯云部署补充环境变量和恢复演练说明。工具仍只提供研究整理和纪律提醒，不执行自动交易。

## 第七、八阶段成品说明

报告中心提供市场、主题、仓位、成交和复盘记录的日期筛选与综合 CSV 导出。上线腾讯云时，建议使用 `deploy/stock-dashboard.service` 管理服务，使用 Nginx 反向代理，仅开放代理端口，并使用 `deploy/backup.cron.example` 定时执行 `backup_server.sh`。恢复时先停止服务，恢复 `decision.db` 和 `data/imports`，再启动服务并检查首页、数据导入页和报告中心。当前工具没有下单接口，不保存券商交易权限。
## 第九、十阶段路线

第九阶段聚焦数据和自动化：统一文件与接口数据格式、检查交易日和数据日期、增量保存收盘快照、生成报告并校验备份。第十阶段聚焦生产化：腾讯云正式部署、访问安全、服务重启、日志、恢复演练、性能优化、移动端体验和长期升级流程。

## 飞书通知（阶段一）

阶段一仅支持看板向飞书群机器人发送手动测试消息；阶段一不支持从飞书发送指令，也不会自动开启任何定时任务。

先在飞书群创建自定义机器人。将它生成的 Webhook URL 设置为运行应用的环境变量；本机 PowerShell 例子如下，尖括号内容请替换为自己的值：

```powershell
$env:FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/<your-webhook-id>"
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8505
```

腾讯云部署时，应在 systemd、Supervisor 或部署平台的密钥管理中设置该环境变量，而不是写进 `app.py`、启动脚本或 Git。不要将 Webhook URL 粘贴到聊天或提交到 Git。

重启看板后，在侧边栏展开“数据源接入”，确认“飞书通知”显示“已配置”，再点击“发送飞书测试通知”。消息只包含测试标识、生成时间和市场数据截至日期；页面不会显示 Webhook URL。若显示“未配置”，点击按钮只会显示配置提示，不会发送网络请求。



