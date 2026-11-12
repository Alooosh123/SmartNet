import os
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_mariadb_transaction_round_trip():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured.")
    engine = create_async_engine(url, pool_pre_ping=True)
    async with engine.begin() as connection:
        result = await connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
        await connection.execute(text(
            "CREATE TABLE IF NOT EXISTS smartnet_ci_probe "
            "(id INT PRIMARY KEY, marker VARCHAR(64) NOT NULL) ENGINE=InnoDB"
        ))
        await connection.execute(text(
            "INSERT INTO smartnet_ci_probe (id, marker) VALUES (1, 'mariadb-transaction-test') "
            "ON DUPLICATE KEY UPDATE marker=VALUES(marker)"
        ))
        marker = await connection.execute(text("SELECT marker FROM smartnet_ci_probe WHERE id=1"))
        assert marker.scalar_one() == "mariadb-transaction-test"
        await connection.execute(text("DELETE FROM smartnet_ci_probe WHERE id=1"))
    await engine.dispose()
