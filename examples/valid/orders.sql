CREATE OR REPLACE VIEW main.commerce.order_kpis
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: main.commerce.orders
fields:
  - name: order_date
    expr: CAST(ordered_at AS DATE)
measures:
  - name: revenue
    expr: SUM(amount)
$$;
