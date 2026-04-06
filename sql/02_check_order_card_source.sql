\timing on


-- ============================================
-- LAB 05: Проверка "истины" в БД для карточки заказа
-- ============================================
--
-- TODO:
-- Замените {{order_id}} на UUID заказа, который тестируете.


SELECT
    o.id,
    o.user_id,
    o.status,
    o.total_amount,
    o.created_at
FROM orders o
WHERE o.id = 'de5893f9-05b1-4bfa-be5e-e132f6205def'::uuid;


SELECT
    oi.order_id,
    oi.product_name,
    oi.price,
    oi.quantity
FROM order_items oi
WHERE oi.order_id = 'de5893f9-05b1-4bfa-be5e-e132f6205def'::uuid
ORDER BY oi.product_name;