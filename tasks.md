# 📌 Subly – Feature Enhancement Roadmap

## 🟢 Phase 1: Core User Expectations (High Priority)
*These features represent immediate user needs and standard SaaS expectations.*

### 🔔 1.1 Reminder & Notification Enhancements
- [x] **1.1.1** Custom reminder offsets (1, 3, 7, 14 days before renewal) — *Implemented via ReminderOffset model*
- [x] **1.1.2** Multiple reminders per subscription — *Supported by dynamic offset list in UI*
- [x] **1.1.3** Per-subscription reminder toggle (on/off) — *Added reminders_enabled toggle to models and forms*

### 🧪 1.2 Trial Management
- [ ] **1.2.1** Trial flag for subscriptions
- [ ] **1.2.2** Trial end date tracking
- [ ] **1.2.3** “Trial ending soon” reminder
- [ ] **1.2.4** Visual badge for trial subscriptions
- [ ] **1.2.5** Auto-convert trial → paid on end date (status update)

### ⏸ 1.3 Subscription Lifecycle Controls
- [ ] **1.3.1** Pause subscription (exclude from reminders & analytics)
- [ ] **1.3.2** Resume paused subscription
- [ ] **1.3.3** Status field: Active / Trial / Paused / Cancelled
- [ ] **1.3.4** Cancelled subscriptions archived (not deleted)

---

## 🟡 Phase 2: Financial Awareness & Control
*Helping users understand and reduce their recurring spending.*

### 💸 2.1 Savings & Cost Insights
- [ ] **2.1.1** Show yearly cost per subscription
- [ ] **2.1.2** “Cancel to save $X/year” indicator
- [ ] **2.1.3** Sort subscriptions by highest cost
- [ ] **2.1.4** Highlight top 3 most expensive subscriptions

### 📈 2.2 Spending Trends
- [ ] **2.2.1** Month-over-month spending comparison
- [ ] **2.2.2** Percentage increase/decrease indicator
- [ ] **2.2.3** Category-wise monthly trends
- [ ] **2.2.4** “New subscription added this month” marker

### 💰 2.3 Price Change Tracking
- [ ] **2.3.1** Track historical price changes
- [ ] **2.3.2** Detect manual price edits
- [ ] **2.3.3** Show price increase/decrease history
- [ ] **2.3.4** Notify on price increase

---

## 🟠 Phase 3: Organization & Usability
*Improving clarity, navigation, and long-term usability.*

### 🗂 3.1 Better Categorization
- [ ] **3.1.1** Custom user-defined categories
- [ ] **3.1.2** Rename categories
- [ ] **3.1.3** Category color tags
- [ ] **3.1.4** Filter dashboard by category

### 🔍 3.2 Search & Filters
- [ ] **3.2.1** Search subscriptions by name
- [ ] **3.2.2** Filter by status (Active / Trial / Paused)
- [ ] **3.2.3** Filter by billing cycle
- [ ] **3.2.4** Filter by category

### 🧾 3.3 Export & Data Portability
- [ ] **3.3.1** Export subscriptions to CSV
- [ ] **3.3.2** Export spending summary (monthly/yearly)
- [ ] **3.3.3** Date-range export
- [ ] **3.3.4** Currency included in exports

---

## 🔵 Phase 4: Account & Platform Enhancements
*Making Subly feel like a professional, complete platform.*

### 🌍 4.1 Currency & Locale
- [ ] **4.1.1** Multi-currency support
- [ ] **4.1.2** User-defined base currency
- [ ] **4.1.3** Manual exchange rate input (initially)
- [ ] **4.1.4** Currency symbol consistency across UI

### 👨‍👩‍👧 4.2 Shared Subscriptions
- [x] **4.2.1** Mark subscription as “Shared”
- [x] **4.2.2** Add participants (emails or names)
- [x] **4.2.3** Cost split (equal / custom)
- [x] **4.2.4** Show personal vs shared spending

### 🔐 4.3 Account Preferences
- [ ] **4.3.1** Timezone selection
- [ ] **4.3.2** Preferred notification time
- [ ] **4.3.3** Default reminder offset
- [ ] **4.3.4** Data deletion / account reset option

---

## 🧱 Phase 5: Engineering & Quality (Silent but Critical)
*Infrastructure improvements that ensure reliability.*

### 🛡 5.1 Reliability & Safety
- [ ] **5.1.1** Strong idempotency for notifications
- [ ] **5.1.2** Renewal date recalculation tests
- [ ] **5.1.3** Edge-case handling (Feb 29, month-end dates)
- [ ] **5.1.4** Soft deletes instead of hard deletes

### ⚙️ 5.2 Performance & Maintainability
- [ ] **5.2.1** Background job abstraction (not OS-specific)
- [ ] **5.2.2** Config-based reminder scheduler
- [ ] **5.2.3** Database indexes for dashboard queries
- [ ] **5.2.4** API rate limiting (basic)

---

## 🏁 Completion Criteria
Before marking a feature as `[x]`:
1. [x] Backend logic implemented
2. [x] UI/UX integrated and verified
3. [x] Edge cases handled
4. [x] Tested with real subscription data