-- O GoTrue administra as tabelas e migracoes, mas espera o schema `auth` ja
-- existente e de posse do usuario dele. NAO pre-crie os tipos (factor_type etc.):
-- a migracao 20221003041349 cria factor_type + factor_status + aal_level num
-- unico bloco DO ... EXCEPTION WHEN duplicate_object; se factor_type ja existe, o
-- bloco pula os outros dois e a tabela mfa_factors quebra ("factor_status does
-- not exist"). Deixe o GoTrue criar todos.
CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION supabase_auth_admin;
ALTER ROLE supabase_auth_admin SET search_path = auth, public;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    CREATE ROLE postgres NOLOGIN;
  END IF;
END
$$;
