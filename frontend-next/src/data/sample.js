// Figures from the Pune Threads sample dataset. Used only by the landing page and the /demo workspace
// (src/demo/), and labelled as a sample in both. Never imported by the merchant app.
export const SAMPLE = {
  shipments: 15370,
  recoverable: 229005,
  findings: 1773,
  rtoCost: 1230968,
  byKind: [
    { label: "Billed weight higher than the parcel", value: 77132 },
    { label: "COD collected, never paid out", value: 58203 },
    { label: "Same parcel billed twice", value: 29721 },
    { label: "RTO charged on delivered parcels", value: 28998 },
    { label: "Billed for a costlier zone", value: 22516 },
    { label: "COD paid short", value: 9050 },
    { label: "COD fee on prepaid orders", value: 3385 },
  ],
  monthlyRto: [32.3, 33.7, 30.3, 31.1, 29.0, 26.6, 23.9, 23.3, 22.4, 20.1, 18.5, 15.2, 18.9, 17.5, 16.0, 18.2, 13.3, 13.1, 16.9, 13.7, 13.3, 11.3, 11.2, 10.3],
  monthLabels: [[0, "Jan 24"], [6, "Jul 24"], [12, "Jan 25"], [18, "Jul 25"], [23, "Dec 25"]],
  zones: ["A", "B", "C", "D", "E"],
  heat: [
    { courier: "SwiftDart Express", values: [13.5, 18.9, 18.4, 26.9, 24.6] },
    { courier: "Ghoda Logistics", values: [14.7, 21.1, 19.8, 28.4, 21.9] },
    { courier: "BlueRoute Couriers", values: [15.5, 22.8, 23.0, 30.2, 28.6] },
  ],
  facts: [
    "34.7% of COD parcels came back, against 3.2% of prepaid",
    "4.1% of everything the couriers billed was wrong",
    "19% of customers brought 46% of delivered revenue",
    "42% of returns sat in the riskiest 10% of orders",
    "45 delivered COD parcels were never paid out",
    "One courier recorded the highest return rate across all five zones",
    "1,069 parcels were billed heavier than they were",
    "8% of customers returned 72.5% of their COD parcels",
  ],
  factors: [
    { label: "Cash on delivery", value: "COD", size: 100 },
    { label: "Delivery zone", value: "E", size: 84 },
    { label: "First-time customer paying COD", value: "Yes", size: 73 },
    { label: "Address detail", value: "almost none", size: 71 },
    { label: "Placed late at night", value: "Yes", size: 35 },
  ],
  monthNames: ["Jan 24","Feb 24","Mar 24","Apr 24","May 24","Jun 24","Jul 24","Aug 24","Sep 24","Oct 24","Nov 24","Dec 24","Jan 25","Feb 25","Mar 25","Apr 25","May 25","Jun 25","Jul 25","Aug 25","Sep 25","Oct 25","Nov 25","Dec 25"],
  // RTO rate cut five ways, for the explorer on the landing page
  cuts: {
    "Payment": [{ label: "Cash on delivery", value: 34.7, note: "7,186 parcels" }, { label: "Prepaid", value: 3.2, note: "8,184 parcels" }],
    "Customer": [{ label: "First order", value: 34.9, note: "4,614 parcels" }, { label: "Repeat order", value: 10.6, note: "10,756 parcels" }],
    "Zone": [{ label: "Zone D · rest of India", value: 28.9 }, { label: "Zone E · North-East, J&K", value: 25.9 }, { label: "Zone B · rest of state", value: 20.8 }, { label: "Zone C · metros", value: 20.1 }, { label: "Zone A · home city", value: 14.2 }],
    "Courier": [{ label: "BlueRoute Couriers", value: 22.8 }, { label: "Ghoda Logistics", value: 18.0 }, { label: "SwiftDart Express", value: 15.7 }],
    "Channel": [{ label: "Instagram Shop", value: 22.0 }, { label: "WhatsApp", value: 16.8 }, { label: "Website", value: 16.2 }],
  },
  cutNotes: {
    "Payment": "Cash on delivery is where returns live. A prepaid parcel almost never comes back.",
    "Customer": "A first order is three times as likely to return as a repeat order.",
    "Zone": "Distance costs twice: far zones are dearer to ship and return more often.",
    "Courier": "Same seller, same products, and a 7-point gap between the best and worst courier.",
    "Channel": "Orders from social shops return more than orders from the seller's own website.",
  },
  // three real orders scored by the model trained on the sample
  orders: [
    { name: "New buyer, vague address", detail: "₹3,200 · COD · Srinagar · 1:20 am · “near temple”", risk: 96.5, band: "Very high", confidence: "Medium",
      action: "Do not ship as COD. Ask the customer to pay online first.",
      factors: [{ label: "Cash on delivery", value: "COD", size: 100 }, { label: "Delivery zone", value: "E", size: 84 }, { label: "First-time customer paying COD", value: "Yes", size: 73 }, { label: "Address detail", value: "almost none", size: 71 }, { label: "Placed late at night", value: "Yes", size: 35 }] },
    { name: "Regular, pays online", detail: "₹899 · Prepaid · Pune · 2:00 pm · full address", risk: 0.4, band: "Low", confidence: "High",
      action: "Ship as usual.",
      factors: [{ label: "Payment", value: "Prepaid", size: 96, effect: "lowers risk" }, { label: "Customer's earlier orders", value: "18", size: 81, effect: "lowers risk" }, { label: "Address detail", value: "complete", size: 26, effect: "lowers risk" }, { label: "First-time customer paying COD", value: "No", size: 20, effect: "lowers risk" }, { label: "Customer's own return rate", value: "0 of 18", size: 16, effect: "lowers risk" }] },
    { name: "Regular with a record of returns", detail: "₹1,500 · COD · Pune · 6 of 18 parcels returned", risk: 7.3, band: "Medium", confidence: "High",
      action: "Confirm the order on WhatsApp or by phone before dispatch. Raised from Low because of the returns on record.",
      factors: [{ label: "Cash on delivery", value: "COD", size: 100 }, { label: "Customer's earlier orders", value: "18", size: 81, effect: "lowers risk" }, { label: "First-time customer paying COD", value: "No", size: 20, effect: "lowers risk" }] },
  ],
  // what refusing COD above each score would have done over the last ten weeks of the sample (908 COD orders)
  thresholds: [[10,703,205,498,-12481],[15,526,179,347,5458],[20,401,151,250,14619],[25,302,131,171,22372],[30,237,114,123,24996],[35,195,100,95,25522],[40,165,86,79,22161],[45,143,77,66,21342],[50,106,59,47,16868],[55,78,46,32,13615],[60,52,31,21,8800],[65,35,24,11,7464],[70,21,15,6,4368],[75,13,8,5,1830],[80,6,4,2,1279]],
};
