# 数据库安装与连接指南

本系统使用 **PostgreSQL 14 + pgvector**。本文档分两部分：
- **第 1 节**：Windows 本地开发环境（你当前的 D:\cnsoft）
- **第 2 节**：银河麒麟 V11 LoongArch 生产环境（部署到大赛虚机）

> SKILL 中已明确锁定 PostgreSQL 14 + pgvector ≥ 0.7.4 + zhparser（V11）+ pg_trgm + uuid-ossp。
> 详见 `SKILL/02-database.md` / `SKILL/05-deployment.md` / `SKILL/16-dependency-compatibility.md`。

---

## 1. Windows 本地开发环境

### 1.1 安装 PostgreSQL 14

去 **EDB 官方页**（https://www.postgresql.org/download/windows/）下载 PostgreSQL 14 Windows 安装包。安装时：

- 安装目录：`D:\PostgreSQL\14`（建议非 C 盘）
- 数据目录：`D:\PostgreSQL\14\data`
- **超级用户密码**：自定义并记牢（下文以 `postgres123` 为例）
- 端口：`5432`（默认）
- 区域：`Chinese (Simplified), China`

装完后 `Stack Builder` 可关掉跳过。

### 1.2 安装 pgvector 扩展（Windows）

Windows 下 pgvector 推荐用预编译方式：

**方式 A：使用社区 Windows 预编译版本（最快）**

1. 去 https://github.com/pgvector/pgvector/releases 找最新 release
2. 寻找类似 `pgvector-x.x.x-pg14-win.zip` 的资产（如果没有则用方式 B）
3. 解压后将文件放入 PostgreSQL 安装目录对应位置：
   - `vector.dll` → `D:\PostgreSQL\14\lib\`
   - `vector.control`、`vector--*.sql` → `D:\PostgreSQL\14\share\extension\`

**方式 B：用预编译 EDB 镜像（推荐）**

国内可访问 [imgix 镜像](https://github.com/pgvector/pgvector#installation-notes) 或直接：

```powershell
# PowerShell
cd $env:TEMP
curl -L -o pgvector.zip https://github.com/pgvector/pgvector/archive/refs/tags/v0.7.4.zip
Expand-Archive pgvector.zip
# 用 VS Build Tools 编译，约 5 分钟
cd pgvector-0.7.4
# 设置 PG_CONFIG 路径
$env:PG_CONFIG = "D:\PostgreSQL\14\bin\pg_config.exe"
nmake /F Makefile.win
nmake /F Makefile.win install
```

**方式 C：用 Docker（最稳，但需要 Docker Desktop）**

如果上述麻烦，临时用 `ankane/pgvector` 镜像（不在本指南范围）。

### 1.3 创建业务数据库 & 启用扩展

打开 `psql` 终端（开始菜单 → PostgreSQL 14 → SQL Shell）。输入超级用户密码后：

```sql
-- 创建业务用户
CREATE USER repair WITH PASSWORD 'CHANGE_ME';

-- 创建业务数据库
CREATE DATABASE repair_system OWNER repair ENCODING 'UTF8';

-- 切换到业务数据库
\c repair_system

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 授权
GRANT ALL ON SCHEMA public TO repair;
```

或者直接跑我们准备好的脚本（更快）：

```powershell
cd D:\cnsoft\repair-system\backend
psql -U postgres -f scripts\init_db.sql
```

> **Windows 本地不装 zhparser**：源码编译困难，会自动降级为 PostgreSQL 默认的 `simple` parser + `ILIKE` 兜底，开发期完全够用。生产环境（V11）再上 zhparser。

### 1.4 配置后端 `.env`

```powershell
cd D:\cnsoft\repair-system\backend
copy .env.local .env
# 用记事本打开 .env，填入你的 DeepSeek API key（其他保持默认）
notepad .env
```

### 1.5 体检 & 启动

```powershell
cd D:\cnsoft\repair-system\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 数据库体检
python scripts\check_db.py

# 看到全部 OK 后初始化业务表 + 默认账号
python scripts\init_db.py

# 启动后端
uvicorn app.main:app --reload --port 8000
```

如果看到日志：

```
数据库连接 OK | PostgreSQL 14.x | 扩展: uuid-ossp,vector,pg_trgm | FTS: simple
```

恭喜，本地环境就绪。打开浏览器访问 http://localhost:5173（前端）登录 `admin/admin123`。

---

## 2. 银河麒麟 V11 LoongArch 生产环境

> 完整步骤详见 `SKILL/05-deployment.md` § 2 与 `SKILL/16-dependency-compatibility.md` § 3.1。下面是简明版。

### 2.1 进虚机后的 30 分钟自检

```bash
uname -m                       # 必须输出 loongarch64
cat /etc/os-release            # 应含 V11
python3 --version              # 应 ≥ 3.11.6
gcc --version                  # 应 ≥ 12.1
yum list available postgresql14-server postgresql14-contrib postgresql14-devel
```

- **yum 全有**：直接 `yum install`
- **yum 缺失**：按 SKILL 16 §3.1 源码编译 PostgreSQL 14（约 20 分钟）

### 2.2 安装顺序

```bash
# 1. PostgreSQL 14（yum 优先，缺失走源码）
sudo yum install -y postgresql14-server postgresql14-contrib postgresql14-devel
sudo /usr/pgsql-14/bin/postgresql-14-setup initdb
sudo systemctl enable --now postgresql-14

# 2. pgvector（必须 0.7+，旧版含 x86 汇编）
git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
cd pgvector
export PG_CONFIG=$(which pg_config)
make && sudo make install

# 3. SCWS + zhparser（中文分词，V11 旧 autotools 不识别 loongarch64）
wget -q -O - http://www.xunsearch.com/scws/down/scws-1.2.3.tar.bz2 | tar xjf -
cd scws-1.2.3
wget -O config.sub   'https://git.savannah.gnu.org/cgit/config.git/plain/config.sub'
wget -O config.guess 'https://git.savannah.gnu.org/cgit/config.git/plain/config.guess'
chmod +x config.sub config.guess
./configure --prefix=/usr/local/scws && make && sudo make install
cd ..
git clone https://github.com/amutu/zhparser.git
cd zhparser
SCWS_HOME=/usr/local/scws make with_llvm=no && sudo make install

# 4. 配置 PG 加载 zhparser
sudo sh -c "echo \"shared_preload_libraries = 'zhparser'\" >> /var/lib/pgsql/14/data/postgresql.conf"
sudo systemctl restart postgresql-14
```

### 2.3 初始化业务库

```bash
sudo -u postgres psql -f /opt/repair-system/backend/scripts/init_db.sql
# 该脚本会自动尝试启用 zhparser；如未编译则跳过（带提示）
```

### 2.4 配置 + 启动

```bash
cd /opt/repair-system/backend
cp .env.v11 .env
vim .env                                       # 替换 SECRET_KEY / LLM_API_KEY / 数据库密码
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python3 scripts/check_db.py                    # 体检
python3 scripts/init_db.py                     # 建表 + 默认账号
sudo systemctl start repair-api                # 由 SKILL 05 §11.1 的 systemd 单元启动
```

---

## 3. 常见排错

| 现象 | 原因 | 处理 |
|---|---|---|
| `connection refused` | PG 服务未启动 | Windows: 服务管理器开启 `postgresql-x64-14`；Linux: `systemctl start postgresql-14` |
| `password authentication failed` | 密码错或 `pg_hba.conf` 不允许 | 检查 `.env` 中 `DATABASE_URL`，或 `pg_hba.conf` 把 `host` 改为 `md5` |
| `extension "vector" is not available` | pgvector 没装 / 未放到 share/extension | 重新检查 1.2 步；或 `\dx` 在 psql 里看已装扩展 |
| `extension "zhparser" is not available` | V11 未编译 zhparser | 走 2.2 步骤 3-4；本地开发可忽略（FTS 自动降级 simple） |
| `pgvector` 安装时 `illegal instruction` | 装了 0.6.x 含 x86 SSE 的旧版 | 必须 ≥ 0.7.4 |
| `psycopg2-binary` 找不到 wheel | LoongArch 没 binary | 项目用 `asyncpg`，不会触发；如手动 pip 装请改 `psycopg2 --no-binary :all:` |
| `check_db.py` 报 `768 维测试失败` | pgvector 没装或维度不匹配 | 在 psql 里 `\dx` 确认 `vector` 已装；`SELECT '[1,2,3]'::vector` 应不报错 |

---

## 4. 数据库设计速查

| 表 | 用途 | 关键字段 |
|---|---|---|
| `users` | 用户（admin / field_worker） | username, password_hash, role |
| `device_types` | 设备类型主数据 | name, category, model_no |
| `cases` | 一线提交案例（审核工作流） | status (pending/approved/rejected), reviewer_id |
| `knowledge_base` | **向量知识库** | content_vector vector(768), source_type (case/manual/experience) |
| `workflow_templates` | 作业流程模板 | steps JSONB, repair_level |
| `repair_records` | 检修记录 | status (in_progress/completed) |
| `feedbacks` | LLM 输出修正反馈 | correction_type |
| `upload_files` | 上传文件记录 | stored_path |
| `kg_entities` | 知识图谱实体 | entity_type, name (UNIQUE) |
| `kg_relations` | 知识图谱关系（三元组） | subject_id, predicate, object_id |

完整表定义见 `backend/app/models/` 及 `SKILL/02-database.md`。
