# 中医诊所管理系统

面向小型中医诊所的一体化管理软件：患者信息登记、门诊/住院（极简出入院）、
药品与治疗项目划价收费、药库出入库。**单机离线运行**，数据全部保存在本机硬盘，
与网络、git 完全无关。

## 技术栈

- 后端：Python + FastAPI + SQLite（单文件库、WAL 模式、事务保护）
- 前端：Vue3 + Element Plus（构建产物由后端托管，目标电脑无需任何环境）
- 打包：PyInstaller 绿色文件夹版，双击即用；更新只替换程序、永不碰数据

## 开发

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-build.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv/Scripts/python run.py                      # 开发试运行 http://127.0.0.1:8321
.venv/Scripts/python scripts/build.py            # 打包（调试版，带控制台窗口）
.venv/Scripts/python scripts/build.py --release  # 打包（发布版，无控制台）
```

## 目录

```
server/     后端（FastAPI 应用、数据层、迁移脚本）
frontend/   前端（当前为占位页，Vue3 工程随后续里程碑建立）
scripts/    打包脚本
数据/       运行时数据（不入库 git）
```

## 里程碑

- [x] M0 项目骨架、SQLite 数据层、打包冒烟
- [x] M1 登录（单管理员）、首启向导、系统设置、备份恢复、A4 打印框架
- [ ] M2 患者档案 + 挂号 + 门诊病历 + A4 打印框架
- [ ] M3 字典（治疗项目/药品/协定处方）+ 项目登记
- [ ] M4 处方开药/付药 + 出入库 + 库存预警
- [ ] M5 药品销售 + 划价收费 + 退费 + 收费凭证打印
- [ ] M6 出入院（极简）+ 出院汇总清单
- [ ] M7 查询中心 + 日结 + 操作留痕
- [ ] M8 迁移助手 + 一键安装/一键更新
- [ ] M9（待定）医保/参合报销
