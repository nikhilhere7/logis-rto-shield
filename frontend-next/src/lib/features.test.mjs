// Plain Node checks (no test framework): node src/lib/features.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_UPLOAD_TYPE, UPLOAD_TYPES, uploadLink, uploadTypeFrom } from "./features.js";

// Every supported ?type= selects exactly that dataset.
const SUPPORTED = { orders: "orders", shipments: "shipments", pincode_zones: "pincode_zones", rate_card: "rate_card", invoices: "invoices", remittances: "remittances" };
for (const [query, expected] of Object.entries(SUPPORTED)) {
  assert.equal(uploadTypeFrom(query), expected, `?type=${query}`);
  assert.equal(uploadLink(query), `/app/uploads?type=${query}`);
}
assert.deepEqual([...UPLOAD_TYPES].sort(), Object.keys(SUPPORTED).sort(), "exactly the six engine types");

// Unknown, missing, empty or differently written values fall back to orders.
for (const query of ["bogus", "pincodes", "rate_cards", "Shipments", " shipments", "", null, undefined]) {
  assert.equal(uploadTypeFrom(query), DEFAULT_UPLOAD_TYPE, `?type=${String(query)}`);
}
assert.equal(DEFAULT_UPLOAD_TYPE, "orders");

// The Uploads page's cards use the same ids, in the same set, so a link can never point at a card that isn't there.
const page = readFileSync(new URL("../pages/Uploads.jsx", import.meta.url), "utf8");
const cards = [...page.matchAll(/^\s*\["([a-z_]+)", "/gm)].map((m) => m[1]);
assert.deepEqual(cards.sort(), [...UPLOAD_TYPES].sort(), "Uploads.jsx cards match UPLOAD_TYPES");

console.log("features.test.mjs: all upload type checks passed");
