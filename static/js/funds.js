const apiURL = "/api/funds";
const f = id => document.getElementById(id);

(async () => {
  let data;
  try {
    const r = await fetch(apiURL);
    data = r.ok ? await r.json() : null;
  } catch {}
  if (!data) {
    data = {
      max_invest_per_coin: 500000,
      buy_amount: 100000,
      max_concurrent_trades: 5,
      slippage_tolerance: 0.001,
      balance_exhausted_action: "알림"
    };
  }
  f("max-per-coin").value = data.max_invest_per_coin;
  f("buy-amount").value = data.buy_amount;
  f("max-trades").value = data.max_concurrent_trades;
  f("slippage").value = data.slippage_tolerance;
  f("balance-action").value = data.balance_exhausted_action;
  document.getElementById("last-saved").textContent =
    data.updated ? new Date(data.updated).toLocaleString() : "-";
})();

document.getElementById("btn-fund-save").onclick = async () => {
  const payload = {
    max_invest_per_coin: +f("max-per-coin").value || 0,
    buy_amount: +f("buy-amount").value || 0,
    max_concurrent_trades: +f("max-trades").value || 1,
    slippage_tolerance: +f("slippage").value || 0,
    balance_exhausted_action: f("balance-action").value,
    updated: new Date().toISOString()
  };
  const res = await fetch(apiURL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    showAlert("자금 설정이 저장되었습니다.");
    const data = await fetch(apiURL).then(r => r.json());
    f("max-per-coin").value = data.max_invest_per_coin;
    f("buy-amount").value = data.buy_amount;
    f("max-trades").value = data.max_concurrent_trades;
    f("slippage").value = data.slippage_tolerance;
    f("balance-action").value = data.balance_exhausted_action;
    document.getElementById("last-saved").textContent =
      data.updated ? new Date(data.updated).toLocaleString() : "-";
    document.dispatchEvent(new CustomEvent("fundsUpdated", { detail: data }));
  } else {
    const err = await res.json().catch(() => ({}));
    showAlert(err.message || "저장 실패", "에러");
  }
};
