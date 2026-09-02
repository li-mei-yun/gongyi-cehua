# Label Studio 本机部署辅助文件

本目录独立于现有业务代码及 Dify。下载来源固定为 Docker Hub 上的官方仓库 `heartexlabs/label-studio`，不使用第三方镜像站。

## 本次部署结果

2026-08-28 已完成官方镜像下载、SHA-256 校验、Docker 导入和本机启动。

- 安装版本：Label Studio 1.23.0。
- 网页验收：`http://localhost:8080/` 跳转至登录页并返回 HTTP 200；浏览器已验证登录和注册页面可显示。
- 持久化挂载已核实；Label Studio 容器运行中，重启次数为 0。
- 部署前后原有 12 个容器的运行状态、启动时间和重启次数保持一致。
- 未创建账户、导入工厂数据或验证实际标注任务；这些需要用户自行登录后继续。
- 此次使用独立下载后导入的方式完成安装，并不代表 Docker Hub 的在线下载网络问题已修复。

## 下载方式

`download_image.py` 使用 Python 标准库，在本次下载连接中使用 TLS 1.2 并验证 HTTPS 证书。它不会修改系统代理、Docker 设置，也不会上传本地图片、曲线或其他文件。

在本目录上一级执行：

```powershell
python label-studio-setup/download_image.py --describe
python label-studio-setup/download_image.py
```

默认使用现有本机代理 `http://127.0.0.1:7897`。通过 `--proxy` 可以指定实际代理地址。保持代理软件运行。

- `image-source.json` 记录固定的 Linux AMD64 镜像摘要及最终归档校验值。
- `official-index.json`、`official-manifest.json`、`official-config.json` 来自官方仓库。
- `image-cache` 保留已校验镜像层和下载中的片段，重复运行会复用校验成功的内容。
- 下载完毕生成 `label-studio-linux-amd64.tar`。中途产生的 `.part` 文件不能导入。
- 镜像层的压缩摘要和解压后摘要均会校验；匿名下载令牌仅保存在进程内存中。

## 导入

脚本显示 `READY` 后，从本目录上一级执行：

```powershell
docker load --input label-studio-setup/label-studio-linux-amd64.tar
```

这只添加 Label Studio 镜像，不停止 Dify。`docker load` 成功后仍需创建并启动 Label Studio 容器。

## 本机实例的约定

- 容器名：`label-studio`。
- 访问地址：`http://localhost:8080`，只绑定本机 `127.0.0.1`。
- 持久化目录：`C:\Users\MGA\Documents\LabelStudio\data`。
- 不共用 Dify 数据库、数据卷或配置文件。
- 初始账号及密码由用户在本机网页自行设置。

单独管理本实例：

```powershell
docker stop label-studio
docker start label-studio
docker logs --tail 100 label-studio
```

不要退出 Docker Desktop 来单独停止 Label Studio，否则 Dify 也可能停止。备份 SQLite 实例时先停止 Label Studio，再复制整个持久化目录；引用的外部原始文件还需另外备份。
