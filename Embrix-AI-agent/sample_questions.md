# Sample Business Queries & Dashboard Architecture

## Dashboard 1: Usage Summary

### 1. Daily Service Usage Trends & Consumption Volume
* **User Question to Ask Agent:** `"Can you show me the daily usage trends and total reading values grouped by service type from service_usage_readings?"`
* **Business Aspect Addressed:** **Usage Trends & Capacity Planning** — Tracks daily cumulative consumption values and total reading counts across service types to identify peak usage patterns, demand growth, and capacity requirements over time.
* **SQL Query:**
```sql
SELECT DATE(latestreadingdate) as usage_date, 
servicetype, 
SUM(readingvalue) as total_reading_value, 
COUNT(*) as record_count 
FROM core_usage.service_usage_readings 
GROUP BY 1,2 
ORDER BY 1;
```

### 2. Batch Execution Reliability & Error Rate Monitoring
* **User Question to Ask Agent:** `"What are the error rate percentages and batch processing statistics for each service type in usage_process_stats?"`
* **Business Aspect Addressed:** **Quality of Service & Pipeline Health** — Monitors batch-level processing statistics and error percentages per service type to detect processing drop-offs, mediation failures, and pipeline bottlenecks.
* **SQL Query:**
```sql
SELECT 
    servicetype as service_type,
    batchid,
    SUM(totalreccount) AS total_records,
    SUM(successreccount) AS successful_records,
    SUM(failurereccount) AS failed_records,
    ROUND((SUM(failurereccount)::DECIMAL / NULLIF(SUM(totalreccount), 0)) * 100, 2) AS error_rate_percentage
FROM core_usage.usage_process_stats
GROUP BY batchid, servicetype
ORDER BY batchid DESC;
```

---

## Dashboard 2: Executive Financial & Customer Monetization

### 1. Sales Channel & Market Segment Pricing Distribution
* **User Question to Ask Agent:** `"How are price offers distributed across sales channels, market segments, and pricing models, along with their average minimum and maximum quantities?"`
* **Business Aspect Addressed:** **Market Segmentation & Pricing Strategy Density** — Evaluates how pricing offers in `core_pricing.price_offer` are distributed across sales channels and market segments, highlighting minimum and maximum quantity thresholds to identify underserved channels or over-saturated pricing tiers.
* **SQL Query:**
```sql
SELECT 
    saleschannel,
    marketsegment,
    pricingmodel,
    COUNT(id) AS offers_count,
    AVG(minimumquantity) AS avg_min_qty,
    AVG(maximumquantity) AS avg_max_qty
FROM core_pricing.price_offer
WHERE saleschannel IS NOT NULL
GROUP BY saleschannel, marketsegment, pricingmodel
ORDER BY offers_count DESC;
```

### 2. Pricing Model & Product Offer Usage Coverage
* **User Question to Ask Agent:** `"How does the number of price offers in core_pricing compare against the actual processed usage volume for each pricing model and service type?"`
* **Business Aspect Addressed:** **Product Offer Adoption & Pricing Alignment** — Correlates price offer portfolio density in `core_pricing` with actual physical consumption records in `core_usage` to evaluate whether pricing models (e.g., recurring vs. transaction-attribute) align with customer usage behavior.
* **SQL Query:**
```sql
SELECT 
    po.pricingmodel,
    po.transactiontype,
    po.servicetype,
    COUNT(po.id) AS price_offers_count,
    COALESCE(SUM(u.totalreccount), 0) AS total_processed_usage
FROM core_pricing.price_offer po
LEFT JOIN (
    SELECT 
        servicetype, 
        SUM(totalreccount) AS totalreccount 
    FROM core_usage.usage_process_stats 
    GROUP BY servicetype
) u ON po.servicetype = u.servicetype
GROUP BY po.pricingmodel, po.transactiontype, po.servicetype
ORDER BY total_processed_usage DESC;
```

### 3. Account Lifetime Revenue & Data Volume (Customer Value Ranking)
* **User Question to Ask Agent:** `"Can you list the top accounts ranked by net transaction value, upload/download data volume, and total journaled revenue?"`
* **Business Aspect Addressed:** **Customer Lifetime Value (CLV) & Unit Economics** — Ranks top-tier enterprise accounts by combining upload/download data volumes and net values from `core_usage` with total recognized revenue in `core_revenue.revenue_journal`.
* **SQL Query:**
```sql
SELECT 
    u.accountid,
    SUM(u.total_upload) AS total_upload_bytes,
    SUM(u.total_download) AS total_download_bytes,
    SUM(u.total_netvalue) AS total_net_value,
    COALESCE(SUM(r.total_rev), 0) AS total_journaled_revenue
FROM (
    SELECT 
        accountid,
        SUM(uploadvolume) AS total_upload,
        SUM(downloadvolume) AS total_download,
        SUM(netvalue) AS total_netvalue
    FROM core_usage.file_detail_record_processed
    WHERE accountid IS NOT NULL
    GROUP BY accountid
) u
LEFT JOIN (
    SELECT 
        accountid,
        SUM(amount) AS total_rev
    FROM core_revenue.revenue_journal
    WHERE accountid IS NOT NULL
    GROUP BY accountid
) r ON u.accountid = r.accountid
GROUP BY u.accountid
ORDER BY total_net_value DESC;
```

---

## Dashboard 3: Operations & Platform Performance

### 1. Order Fulfillment Velocity & Turnaround Time
* **User Question to Ask Agent:** `"What is the average order fulfillment turnaround time in hours broken down by order source and subscription reason?"`
* **Business Aspect Addressed:** **Operational Efficiency & Order Fulfillment Velocity** — Measures turn-around duration between order creation and completion in `core_oms.order` by order source and subscription reason to uncover operational bottlenecks in customer onboarding.
* **SQL Query:**
```sql
SELECT 
    source,
    subscriptionreason,
    status,
    COUNT(id) AS total_orders,
    AVG(EXTRACT(EPOCH FROM (completeddate - createddate))/3600) AS avg_fulfillment_hours
FROM core_oms.order
WHERE completeddate IS NOT NULL AND createddate IS NOT NULL
GROUP BY source, subscriptionreason, status
ORDER BY total_orders DESC;
```

### 2. Active Order Subscription & Service Usage Alignment (Churn & Inactivity Risk)
* **User Question to Ask Agent:** `"Which active orders and accounts in Order Management have low or zero successful usage records in core_usage?"`
* **Business Aspect Addressed:** **Customer Churn Risk & Account Inactivity** — Cross-references active order subscriptions in Order Management (`core_oms`) with actual processing activity in `core_usage` to detect dormant accounts or underutilized subscriptions before churn occurs.
* **SQL Query:**
```sql
SELECT 
    o.id AS order_id,
    o.accountid AS account_id,
    o.status AS order_status,
    s.servicetype AS service_type,
    COALESCE(u.success_recs, 0) AS total_successful_usage_records
FROM core_oms.order o
JOIN core_oms.order_services s ON o.id = s.instanceid OR o.id = s.provisioningid
LEFT JOIN (
    SELECT 
        servicetype, 
        SUM(successreccount) AS success_recs 
    FROM core_usage.usage_process_stats 
    GROUP BY servicetype
) u ON s.servicetype = u.servicetype
WHERE o.status = 'ACTIVE' OR o.status IS NOT NULL;
```
