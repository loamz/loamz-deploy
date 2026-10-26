# Uptime Monitoring, Status Page & Host Alarms (Runbook)

*Step-by-step setup guide for the service owner to configure zero-cost monitoring and automated alerts.*

---

## 1. Free Uptime Monitoring (Every 5 Minutes with Email Alerts)

We evaluated two reputable free monitoring services on **2026-10-26**:

1. **UptimeRobot** (Source: [uptimerobot.com/pricing](https://uptimerobot.com/pricing), checked 2026-10-26):
   - **Free tier limits:** 50 monitors, 5-minute check interval, email alerts, 1 public status page with custom domain.
2. **Better Stack Uptime** (Source: [betterstack.com/uptime/pricing](https://betterstack.com/uptime/pricing), checked 2026-10-26):
   - **Free tier limits:** 10 monitors, 3-minute check interval, email alerts, basic status page.

**Chosen Service:** **UptimeRobot**  
*Reason:* The 50-monitor allowance comfortably covers our current endpoints and future growth, the 5-minute interval matches our operational requirement without hitting paywalls, and it provides a free custom-domain status page (`status.loamz.com`).

---

### Step-by-Step Configuration in UptimeRobot

#### Step 1.1: Create Account & Alert Contact
1. Navigate to `https://uptimerobot.com` and click **Register for FREE**.
2. Sign up using the owner email: `ravikumarchavva@outlook.com`.
3. Verify your email address by clicking the activation link sent to your inbox.
4. In the UptimeRobot dashboard, navigate to **My Settings** > **Alert Contacts**.
5. Verify that your default email contact (`ravikumarchavva@outlook.com`) has a status of **Active** (green checkmark).

#### Step 1.2: Add Monitor 1 — Loamz Chat Web & Healthz
1. In the top navigation, click **+ Add New Monitor**.
2. Fill in the following exact fields:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `Loamz Chat Healthz`
   - **URL (or IP):** `https://chat.loamz.com/healthz`
   - **Monitoring Interval:** `Every 5 minutes`
   - **Monitor Timeout:** `30 seconds`
   - **Select "Alert Contacts To Notify":** Check the box next to `ravikumarchavva@outlook.com`.
3. Click **Create Monitor**.

#### Step 1.3: Add Monitor 2 — Keycloak OIDC Discovery Endpoint
1. Click **+ Add New Monitor**.
2. Fill in the following exact fields:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `Loamz Auth Keycloak OIDC`
   - **URL (or IP):** `https://auth.loamz.com/realms/loamz/.well-known/openid-configuration`
   - **Monitoring Interval:** `Every 5 minutes`
   - **Monitor Timeout:** `30 seconds`
   - **Select "Alert Contacts To Notify":** Check the box next to `ravikumarchavva@outlook.com`.
3. Click **Create Monitor**.

> **How you know it worked:**  
> In your UptimeRobot dashboard, both `Loamz Chat Healthz` and `Loamz Auth Keycloak OIDC` will transition from grey to green with status **Up (100%)**. You will receive an email confirmation from UptimeRobot confirming the active monitors.

---

## 2. Public Status Page at `status.loamz.com`

### Step 2.1: Create Status Page in UptimeRobot
1. In the UptimeRobot dashboard, click **Status Pages** in the left menu.
2. Click **+ Add Status Page**.
3. Fill in the following exact fields:
   - **Name:** `Loamz Chat Status`
   - **Monitors:** Select both `Loamz Chat Healthz` and `Loamz Auth Keycloak OIDC`.
   - **Custom Domain:** `status.loamz.com`
4. Click **Create Status Page**.

### Step 2.2: Add DNS Record at DNS Provider
1. Log in to your DNS management console for the domain `loamz.com` (Cloudflare, Route 53, or your registrar).
2. Create a new DNS record:
   - **Type:** `CNAME`
   - **Name / Host:** `status`
   - **Value / Target:** `stats.uptimerobot.com`
   - **TTL:** `Auto` (or `300` / 5 minutes)
   - **Proxy status:** If using Cloudflare, set to **DNS Only** (grey cloud) so UptimeRobot can verify SSL.
3. Save the DNS record.

> **How you know it worked:**  
> Open a browser and visit `https://status.loamz.com`. You should see the public "Loamz Chat Status" dashboard listing both services as operational, with response time graphs and 90-day uptime bars.

---

## 3. Oracle Cloud Infrastructure (OCI) Host Alarms

Oracle Monitoring offers automated alarms that fire whenever host metrics exceed safety thresholds.

### Step 3.1: Create an OCI Notifications Topic & Email Subscription
1. Sign in to the **Oracle Cloud Console** (`https://cloud.oracle.com`).
2. Open the navigation menu (top-left hamburger), select **Developer Services**, and click **Notifications**.
3. Select your compartment (e.g. `root` or `loamz`).
4. Click **Create Topic**:
   - **Name:** `loamz-alerts`
   - **Description:** `Production alerts for Loamz Chat VM host`
   - Click **Create**.
5. Click on the newly created `loamz-alerts` topic.
6. Under **Subscriptions** on the left, click **Create Subscription**:
   - **Protocol:** `EMAIL`
   - **Email:** `ravikumarchavva@outlook.com`
   - Click **Create**.
7. **Action required:** Check `ravikumarchavva@outlook.com` for an email from Oracle Notification Service titled *"Please confirm your subscription"*. Click the **Confirm subscription** link inside the email.

---

### Step 3.2: Create Alarm 1 — CPU Utilization Above 85%
1. Open the navigation menu, select **Observability & Management**, and click **Alarm Definitions** (under Monitoring).
2. Click **Create Alarm**:
   - **Alarm Name:** `loamz-vm-high-cpu`
   - **Alarm Severity:** `Critical`
   - **Metric Compartment:** Your VM compartment (e.g., `root` or `loamz`).
   - **Metric Namespace:** `oci_computeagent`
   - **Metric Name:** `CpuUtilization`
   - **Interval:** `5m`
   - **Statistic:** `Mean`
   - **Operator:** `greater than` (`>`)
   - **Threshold value:** `85`
3. Under **Notification**, configure:
   - **Destination Service:** `Notifications Service`
   - **Compartment:** Your compartment
   - **Topic:** Select `loamz-alerts`
   - **Repeat notification every:** `30` minutes
4. Click **Save Alarm**.

---

### Step 3.3: Create Alarm 2 — Memory Utilization Above 90%
1. On the **Alarm Definitions** page, click **Create Alarm**:
   - **Alarm Name:** `loamz-vm-high-memory`
   - **Alarm Severity:** `Critical`
   - **Metric Compartment:** Your VM compartment
   - **Metric Namespace:** `oci_computeagent`
   - **Metric Name:** `MemoryUtilization`
   - **Interval:** `5m`
   - **Statistic:** `Mean`
   - **Operator:** `greater than` (`>`)
   - **Threshold value:** `90`
2. Under **Notification**, configure:
   - **Destination Service:** `Notifications Service`
   - **Topic:** Select `loamz-alerts`
   - **Repeat notification every:** `30` minutes
3. Click **Save Alarm**.

---

### Step 3.4: Create Alarm 3 — Disk Space Utilization Above 80%
1. On the **Alarm Definitions** page, click **Create Alarm**:
   - **Alarm Name:** `loamz-vm-high-disk`
   - **Alarm Severity:** `Warning`
   - **Metric Compartment:** Your VM compartment
   - **Metric Namespace:** `oci_computeagent`
   - **Metric Name:** `DiskUtilization`
   - **Interval:** `5m`
   - **Statistic:** `Mean`
   - **Operator:** `greater than` (`>`)
   - **Threshold value:** `80`
2. Under **Notification**, configure:
   - **Destination Service:** `Notifications Service`
   - **Topic:** Select `loamz-alerts`
   - **Repeat notification every:** `60` minutes
3. Click **Save Alarm**.

---

> **How you know it worked:**  
> In the OCI Console under **Observability & Management > Alarm Definitions**, all three alarms (`loamz-vm-high-cpu`, `loamz-vm-high-memory`, `loamz-vm-high-disk`) will show a status of **OK** (green indicator). If the CPU, RAM, or root disk crosses the configured threshold for more than 5 minutes, an automated email alert from `oracle-notifications@oracle.com` will immediately land in `ravikumarchavva@outlook.com`.

---

### Sources & Facts Verification
- **UptimeRobot free tier limits:** Verified on `https://uptimerobot.com/pricing/` on 2026-10-26 (50 monitors, 5-minute interval, free status page).
- **Better Stack free tier limits:** Verified on `https://betterstack.com/uptime/pricing` on 2026-10-26 (10 monitors, 3-minute interval).
- **OCI Compute Agent Metrics:** Oracle Cloud Infrastructure Monitoring documentation for `oci_computeagent` (`CpuUtilization`, `MemoryUtilization`, `DiskUtilization`).
- **Owner email:** `AGENTS.md` (author: `Ravikumarchavva <ravikumarchavva@outlook.com>`).
- **Endpoints:** `https://chat.loamz.com/healthz` (`crates/chat-server/src/main.rs`), `https://auth.loamz.com/realms/loamz/.well-known/openid-configuration` (`deploy/ansible/group_vars/all.yml`).
