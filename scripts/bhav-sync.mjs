// Copies Talwar Jewellery House's daily 24K and 22K board rates from Bhav
// into data/gold-rates.json, which the website's gold rate page reads.
// Uses Bhav's read-only public function bhav_public_state. Only the two
// rates and the time they were set are stored; nothing else from Bhav.
import { readFile, writeFile } from "node:fs/promises"

const FILE = "data/gold-rates.json"
const KEEP_DAYS = 400
const base = (process.env.BHAV_SUPABASE_URL || "").replace(/\/+$/, "")
const key = process.env.BHAV_PUBLISHABLE_KEY || ""

if (!base || !key) {
    console.log("::notice::Bhav connection not configured (BHAV_SUPABASE_URL / BHAV_PUBLISHABLE_KEY). Skipping.")
    process.exit(0)
}

const res = await fetch(base + "/rest/v1/rpc/bhav_public_state", {
    method: "POST",
    headers: { apikey: key, "Content-Type": "application/json" },
    body: "{}",
})
if (!res.ok) {
    console.log(`::error::Bhav returned HTTP ${res.status}`)
    process.exit(1)
}
const s = await res.json()
const rate24 = Number(s.rate24)
const rate22 = Number(s.rate22)

// Never publish an implausible or unset rate (22K must sit just below 24K).
if (!(rate24 > 0 && rate22 > 0 && rate22 < rate24 && rate22 > rate24 * 0.85) || !s.setAt) {
    console.log(`::warning::Skipping implausible or unset rate (24K ${s.rate24}, 22K ${s.rate22}, set ${s.setAt}).`)
    process.exit(0)
}

const setAt = new Date(s.setAt).toISOString()
const date = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(setAt))

let data
try {
    data = JSON.parse(await readFile(FILE, "utf8"))
} catch {
    data = { source: "Talwar Jewellery House board rate", unit: "INR per gram", latest: null, days: [] }
}

const day = { date, rate24, rate22, setAt }
const days = [day, ...(data.days || []).filter((d) => d.date !== date)]
    .sort((a, b) => (a.date < b.date ? 1 : -1))
    .slice(0, KEEP_DAYS)
const next = { ...data, latest: days[0], days }

if (JSON.stringify(next) === JSON.stringify(data)) {
    console.log(`No change (${date}: 24K ₹${rate24}/g, 22K ₹${rate22}/g).`)
    process.exit(0)
}
await writeFile(FILE, JSON.stringify(next, null, 1) + "\n")
console.log(`Updated ${date}: 24K ₹${rate24}/g, 22K ₹${rate22}/g.`)
