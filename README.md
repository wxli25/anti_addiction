# 防沉迷守卫 Anti-Addiction Guard

Windows 游戏时间管理工具，帮助限制每日游戏时长，适合家长管理孩子的游戏时间。

## 功能

- 监控指定游戏/程序的每日运行时长
- 超出时限后自动关闭程序并弹出提醒
- 密码保护，防止配置被修改
- 最小化到系统托盘，后台静默运行
- 支持开机自动启动

## 安装依赖

```bash
pip install psutil pystray Pillow
```

## 运行

```bash
python anti_addiction.py
```

## 使用说明

1. 点击「＋ 添加程序」，选择游戏的 `.exe` 文件
2. 设置每日时限（分钟）
3. 点击「设置密码」保护配置不被修改
4. 点击「最小化到托盘」让程序在后台运行

## 依赖

- Python 3.x
- psutil
- pystray
- Pillow
