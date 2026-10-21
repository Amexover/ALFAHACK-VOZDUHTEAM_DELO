import assert from 'node:assert/strict';
const base = (process.env.BASE_URL || 'http://195.133.41.30').replace(/\/$/, '');
let checks = 0;
async function request(path, {method='GET', body, cookie, status=200} = {}) {
 const r=await fetch(base+path,{method,headers:{...(body?{'Content-Type':'application/json'}:{}),...(cookie?{Cookie:cookie}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
 assert.equal(r.status,status,`${method} ${path}: expected ${status}, got ${r.status}`); checks++;
 return r;
}
async function login(name){const r=await request('/api/auth/login',{method:'POST',body:{login:name,password:'demo'}});const cookie=r.headers.getSetCookie().find(x=>x.startsWith('session='))?.split(';')[0];assert.ok(cookie,`No session cookie for ${name}`);checks++;return cookie}
const html=await(await request('/')).text();assert.match(html,/Дело/);checks++;
for(const asset of [...html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g)].map(x=>x[1]))await request(asset);
await request('/companies/1');await request('/docs');
const schema=await(await request('/api/openapi.json')).json();assert.ok(schema.paths['/api/applications/{application_id}/submit']);checks++;
const health=await(await request('/api/health')).json();assert.equal(health.status,'ok');checks++;
await request('/api/companies',{status:401});await request('/api/staff/applications',{status:401});
const alexey=await login('alexey'),maria=await login('maria'),staff=await login('staff');
const companies=(await(await request('/api/companies',{cookie:alexey})).json()).items;
const ip=companies.find(c=>c.legal_form==='IP');assert.ok(ip);checks++;
const dashboard=await(await request(`/api/companies/${ip.id}/dashboard`,{cookie:alexey})).json();assert.ok(dashboard.rating===null||typeof dashboard.rating.score==='number');checks++;
await request(`/api/companies/${ip.id}/dashboard`,{cookie:maria,status:404});
await request('/api/staff/applications',{cookie:alexey,status:403});await request('/api/companies',{cookie:staff,status:403});await request('/api/staff/applications',{cookie:staff});
const quote=await(await request('/api/pricing/quote',{method:'POST',cookie:alexey,body:{company_id:ip.id,borrowing_mode:'NEW_CREDIT',amount:1500000,term_months:24}})).json();
assert.equal(quote.rate,dashboard.rating?18:24);assert.ok(quote.monthly_payment>0);checks+=2;
await request('/api/pricing/quote',{method:'POST',cookie:alexey,body:{company_id:ip.id,borrowing_mode:'NEW_CREDIT',amount:3500000,term_months:24},status:422});
const news=(await(await request(`/api/news?company_id=${ip.id}`,{cookie:alexey})).json()).items;assert.equal(news.length,6);checks++;await request(`/api/news/${news[0].id}`,{cookie:alexey});await request('/api/support');
console.log(JSON.stringify({base,checks,result:'PASS',scope:'Read-only HTTP smoke + synthetic demo login; no applications created or reset'},null,2));
