"""Core realtime trading interfaces for Binance USDS-M trend system.

v1.7 includes a Binance futures testnet broker adapter. Live/mainnet execution
remains unimplemented; broker-specific behavior must stay isolated in
BrokerAdapter implementations.
"""

from .brokers import (
    BinanceTestnetBroker,
    BinanceTestnetCredentials,
    BrokerAdapter,
    PaperBroker,
    RejectingBrokerAdapter,
    TestnetRiskLimits,
    redact_sensitive_testnet_fields,
    resolve_binance_testnet_credentials,
)
from .evolution import build_runtime_replay_dataset, compare_runtime_strategy_variants, load_runtime_records
from .execution import ExecutionEngine, ExecutionPlan, OrderInstruction, PaperIntentExecutionEngine
from .loop import TradingCycleConfig, run_trading_cycle
from .market_data import FunctionMarketData, MarketData
from .portfolio import PortfolioPosition, PortfolioState
from .risk import FunctionRiskManager, RiskManager
from .runtime import FunctionRuntimeRecorder, RuntimeRecorder
from .signals import FunctionSignalEngine, SignalEngine
from .strategy import TrendParticipationStrategy, Strategy
from .types import MarketDataRequest, StrategyIntent

__all__ = [
    "BinanceTestnetBroker",
    "BinanceTestnetCredentials",
    "BrokerAdapter",
    "ExecutionEngine",
    "ExecutionPlan",
    "FunctionMarketData",
    "FunctionRiskManager",
    "FunctionRuntimeRecorder",
    "FunctionSignalEngine",
    "MarketData",
    "MarketDataRequest",
    "OrderInstruction",
    "PaperBroker",
    "PaperIntentExecutionEngine",
    "PortfolioPosition",
    "PortfolioState",
    "RejectingBrokerAdapter",
    "RiskManager",
    "RuntimeRecorder",
    "SignalEngine",
    "Strategy",
    "StrategyIntent",
    "TrendParticipationStrategy",
    "TradingCycleConfig",
    "TestnetRiskLimits",
    "build_runtime_replay_dataset",
    "compare_runtime_strategy_variants",
    "load_runtime_records",
    "redact_sensitive_testnet_fields",
    "resolve_binance_testnet_credentials",
    "run_trading_cycle",
]
