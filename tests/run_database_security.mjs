// Optional local PostgreSQL-engine test; PGLITE_MODULE points to an installed PGlite module.
import {readFile} from 'node:fs/promises';
const {PGlite}=await import(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const db=new PGlite();
await db.exec(`create role anon; create role authenticated; create schema auth;
create table auth.users(id uuid primary key,email text);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
create function auth.jwt() returns jsonb language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$;
grant usage on schema auth,public to authenticated,anon; grant execute on function auth.uid(),auth.jwt() to authenticated,anon;`);
for(const file of ['supabase/migrations/202609120001_legal_workbench.sql','supabase/migrations/202609130001_account_security.sql','supabase/migrations/202609130002_profiles.sql','supabase/migrations/202609130003_ai_allowances.sql','supabase/migrations/202609130003_ai_allowances.sql','supabase/tests/ai_allowances.sql','supabase/tests/workbench_rls.sql','supabase/tests/account_rls.sql']){
 await db.exec(await readFile(file,'utf8'));
}
console.log('PASS: existing-table hardening and cross-user CRUD/RLS tests.');
await db.close();
