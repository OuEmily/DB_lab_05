-- ============================================
-- Схема базы данных маркетплейса
-- ============================================

-- Включаем расширение UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- TODO: Создать таблицу order_statuses
-- Столбцы: status (PK), description

CREATE TABLE IF NOT EXISTS order_statuses (
    status TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

-- TODO: Вставить значения статусов
-- created, paid, cancelled, shipped, completed

INSERT INTO order_statuses (status, description) VALUES 
    ('created', 'Заказ создан'),
    ('paid', 'Заказ оплачен'),
    ('cancelled', 'Заказ отменен'),
    ('shipped', 'Заказ доставляется'),
    ('completed', 'Заказ завершён')
ON CONFLICT (status) DO NOTHING;

-- TODO: Создать таблицу users
-- Столбцы: id (UUID PK), email, name, created_at
-- Ограничения:
--   - email UNIQUE
--   - email NOT NULL и не пустой
--   - email валидный (regex через CHECK)

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email  TEXT NOT NULL UNIQUE
        CHECK (email <> '' AND email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() 
);

-- TODO: Создать таблицу orders
-- Столбцы: id (UUID PK), user_id (FK), status (FK), total_amount, created_at
-- Ограничения:
--   - user_id -> users(id)
--   - status -> order_statuses(status)
--   - total_amount >= 0

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL REFERENCES order_statuses(status),
    total_amount NUMERIC(10, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- TODO: Создать таблицу order_items
-- Столбцы: id (UUID PK), order_id (FK), product_name, price, quantity
-- Ограничения:
--   - order_id -> orders(id) CASCADE
--   - price >= 0
--   - quantity > 0
--   - product_name не пустой

CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_name TEXT NOT NULL
        CHECK (product_name <> ''),
    price NUMERIC(10, 2) NOT NULL
        CHECK (price >= 0),
    quantity INT NOT NULL
        CHECK (quantity > 0)
);

-- TODO: Создать таблицу order_status_history
-- Столбцы: id (UUID PK), order_id (FK), status (FK), changed_at
-- Ограничения:
--   - order_id -> orders(id) CASCADE
--   - status -> order_statuses(status)

CREATE TABLE IF NOT EXISTS order_status_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    status TEXT NOT NULL REFERENCES order_statuses(status),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- КРИТИЧЕСКИЙ ИНВАРИАНТ: Нельзя оплатить заказ дважды
-- ============================================
-- TODO: Создать функцию триггера check_order_not_already_paid()
-- При изменении статуса на 'paid' проверить что его нет в истории
-- Если есть - RAISE EXCEPTION

CREATE OR REPLACE FUNCTION check_order_not_already_paid() RETURNS TRIGGER AS $$
    BEGIN
        IF (NEW.status = 'paid') THEN
            IF EXISTS (
                SELECT 1 FROM order_status_history
                WHERE order_id = NEW.id AND status = 'paid'
            ) THEN
                RAISE EXCEPTION 'Заказ уже оплачен!';
            END IF;
        END IF;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;

-- TODO: Создать триггер trigger_check_order_not_already_paid
-- BEFORE UPDATE ON orders FOR EACH ROW

CREATE TRIGGER trigger_check_order_not_already_paid
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION check_order_not_already_paid();

-- ============================================
-- БОНУС (опционально)
-- ============================================
-- TODO: Триггер автоматического пересчета total_amount

--CREATE OR REPLACE FUNCTION recalculate_total_amount() RETURNS TRIGGER AS $$
--    BEGIN
--        UPDATE orders
--        SET total_amount = (
--            SELECT COALESCE(SUM(price * quantity), 0) FROM order_items
--            WHERE order_id = COALESCE(NEW.order_id, OLD.order_id)
  --      )
--        WHERE id = COALESCE(NEW.order_id, OLD.order_id);
--        RETURN NEW;
--    END;
--$$ LANGUAGE plpgsql;

--CREATE TRIGGER trigger_recalculate_total_amount
 --   AFTER INSERT OR UPDATE OR DELETE ON order_items
 --   FOR EACH ROW
--    EXECUTE FUNCTION recalculate_total_amount();

-- TODO: Триггер автоматической записи в историю при изменении статуса

----

--CREATE OR REPLACE FUNCTION record_in_changing_status() RETURNS TRIGGER AS $$
--    BEGIN
--       IF OLD.status IS DISTINCT FROM NEW.status THEN
--            INSERT INTO order_status_history (order_id, status, changed_at)
--            VALUES (NEW.id, NEW.status, CURRENT_TIMESTAMP);
--        END IF;
--        RETURN NEW;
--    END;
--$$ LANGUAGE plpgsql;

--CREATE TRIGGER trigger_record_in_changing_status
--    AFTER UPDATE OF status ON orders
--    FOR EACH ROW
--    EXECUTE FUNCTION record_in_changing_status();
-------

-- TODO: Триггер записи начального статуса при создании заказа

--CREATE OR REPLACE FUNCTION record_status_new_order() RETURNS TRIGGER AS $$
 --   BEGIN
 --       INSERT INTO order_status_history (order_id, status, changed_at)
 --       VALUES (NEW.id, NEW.status, CURRENT_TIMESTAMP);
 --       RETURN NEW;
 --   END;
--$$ LANGUAGE plpgsql;

--CREATE TRIGGER trigger_record_status_new_order
  --  AFTER INSERT ON orders
    --FOR EACH ROW
    --EXECUTE FUNCTION record_status_new_order();