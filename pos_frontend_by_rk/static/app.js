const state = { cart: [] };
async function fetchStock() {
  const r = await fetch(`${window.config.backend_url}/pos/stock`);
  if (!r.ok) { alert('Failed to load stock'); return; }
  renderCatalog(await r.json());
}
function renderCatalog(items){
  const el = document.getElementById('catalog');
  el.innerHTML = items.map(p => `
    <div class="card">
      <h3>${p.name || p.product_id}</h3>
      <div class="price">${p.base_price || ''} NOK</div>
      <button onclick="addToCart('${p.product_id||''}','${p.short_id||''}', ${Number(p.base_price||0)})">Add</button>
    </div>`).join('');
}
function addToCart(product_id, short_id, price){ state.cart.push({product_id, short_id, price, qty:1}); renderCart(); }
function renderCart(){
  const c = document.getElementById('cartItems');
  c.innerHTML = state.cart.map((i,idx)=>`
    <div>${i.product_id||i.short_id} x ${i.qty} = ${(i.qty*i.price).toFixed(2)} NOK 
      <button onclick="inc(${idx})">+</button>
      <button onclick="dec(${idx})">-</button>
    </div>`).join('');
}
function inc(i){ state.cart[i].qty++; renderCart(); }
function dec(i){ state.cart[i].qty=Math.max(1,state.cart[i].qty-1); renderCart(); }
async function checkout(){
  if(state.cart.length===0){ alert('Cart empty'); return; }
  const line = state.cart[0];
  const payload = { reseller_id: '', product_id: line.product_id, short_id: line.short_id, qty: line.qty, customer_id: 'C-000', payment_method: 'cash' };
  const r = await fetch(`${window.config.backend_url}/pos/sale`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  if(!r.ok){ const e=await r.text(); alert('Sale failed: '+e); return; }
  const res = await r.json(); alert('Sale OK. Total: '+res.total+' NOK'); state.cart = []; renderCart();
}
document.getElementById('checkoutBtn').addEventListener('click', checkout);
fetchStock();
