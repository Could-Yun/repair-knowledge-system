-- ============================================================
-- 数据库初始化 SQL（DBA 级，需 postgres 超级用户执行）
-- 作用：创建业务用户 / 业务数据库 / 启用扩展
-- 表结构由 SQLAlchemy(Base.metadata.create_all) 创建，本文件不建表
-- ============================================================
-- 用法（Windows）：
--   psql -U postgres -f scripts\init_db.sql
-- 用法（V11 / Linux）：
--   sudo -u postgres psql -f scripts/init_db.sql
-- ============================================================

-- 1. 创建业务用户（如已存在则忽略）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'repair') THEN
        CREATE USER repair WITH PASSWORD 'CHANGE_ME';
        RAISE NOTICE '用户 repair 创建成功（默认密码 CHANGE_ME，生产环境请修改！）';
    ELSE
        RAISE NOTICE '用户 repair 已存在，跳过';
    END IF;
END $$;

-- 2. 创建业务数据库
SELECT 'CREATE DATABASE repair_system OWNER repair ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'repair_system')\gexec

GRANT ALL PRIVILEGES ON DATABASE repair_system TO repair;

-- 3. 切换到业务数据库
\c repair_system

-- 4. 启用扩展（在业务库中，仍需 superuser）
--    SKILL 02 §1
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector ≥ 0.7.4
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- 设备型号 LIKE 索引

-- zhparser（仅 V11 LoongArch 生产环境有意义；Windows 本地装不上则跳过）
-- 若 shared_preload_libraries 已含 zhparser 则启用
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS zhparser;
        IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese') THEN
            CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
            ALTER TEXT SEARCH CONFIGURATION chinese
                ADD MAPPING FOR n,v,a,i,e,l WITH simple;
            RAISE NOTICE 'zhparser + chinese 配置已创建（V11 生产环境就绪）';
        END IF;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'zhparser 未安装（本地开发可忽略，FTS 将走 simple parser）';
    END;
END $$;

-- 5. 业务用户授权
GRANT ALL ON SCHEMA public TO repair;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO repair;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO repair;

-- 6. 体检报告
SELECT
    current_database()                                    AS database,
    current_user                                          AS connected_as,
    (SELECT string_agg(extname, ', ') FROM pg_extension)  AS installed_extensions,
    (SELECT count(*) FROM pg_ts_config WHERE cfgname IN ('chinese','simple')) AS ts_configs;
