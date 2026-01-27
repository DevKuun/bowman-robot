-- Initialize database schema for Bowman Robot
-- This script runs automatically when PostgreSQL container starts

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Exchange accounts table
CREATE TABLE IF NOT EXISTS exchange_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange VARCHAR(50) NOT NULL,
    access_key_encrypted TEXT NOT NULL,
    secret_key_encrypted TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_valid_key BOOLEAN DEFAULT TRUE NOT NULL,
    is_correct_ip BOOLEAN DEFAULT TRUE NOT NULL,
    is_checked BOOLEAN DEFAULT TRUE NOT NULL,
    risk_level INTEGER DEFAULT 1 NOT NULL CHECK (risk_level >= 0 AND risk_level <= 4),
    cash_weight DECIMAL(5,4) DEFAULT 0.0 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, exchange)
);

-- Portfolio weights table
CREATE TABLE IF NOT EXISTS portfolio_weights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    risk_level INTEGER NOT NULL,
    weights JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Trades table
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange_account_id UUID REFERENCES exchange_accounts(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    price DECIMAL(20,8) NOT NULL,
    status VARCHAR(20) NOT NULL,
    exchange_order_id VARCHAR(100),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    executed_at TIMESTAMP
);

-- System config table
CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- PnL snapshots table (for portfolio value history)
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    session_id VARCHAR(50) NOT NULL,
    total_value DECIMAL(20,2) NOT NULL,
    pnl DECIMAL(20,2) NOT NULL,
    pnl_percent DECIMAL(10,4) NOT NULL,
    initial_value DECIMAL(20,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_exchange_accounts_active ON exchange_accounts(is_active, exchange);
CREATE INDEX IF NOT EXISTS idx_portfolio_weights_latest ON portfolio_weights(exchange, risk_level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(exchange_account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pnl_snapshots_session ON pnl_snapshots(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pnl_snapshots_exchange ON pnl_snapshots(exchange, created_at DESC);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_exchange_accounts_updated_at BEFORE UPDATE ON exchange_accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_config_updated_at BEFORE UPDATE ON system_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default system config
INSERT INTO system_config (key, value, description) VALUES
    ('portfolio_optimization_interval', '604800', 'Portfolio optimization interval in seconds (1 week)'),
    ('db_refresh_interval', '5', 'Database refresh interval in seconds'),
    ('binance_refresh_interval', '3', 'Binance price refresh interval in seconds')
ON CONFLICT (key) DO NOTHING;

-- Grant permissions (if needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
