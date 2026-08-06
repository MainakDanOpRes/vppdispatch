"""
Batch Dispatch Service for VPP Optimization
Handles parallel optimization for multiple customers.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Union, Tuple
import logging

from ..models.schemas import CustomerConfig
from .dispatch_service import run_multi_asset_dispatch

logger = logging.getLogger(__name__)

def run_batch_dispatch(
    customer_configs: List[Union[CustomerConfig, dict]],
    max_workers: int = 4,
    batt_degradation_cost: float = 0.01,
    timeout: Optional[float] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Run batch dispatch for multiple customers with dynamic asset configuration.

    Uses ThreadPoolExecutor for parallel processing. Each customer's optimization
    runs in a separate thread, allowing multiple optimizations to run concurrently.

    Args:
        customer_configs: List of CustomerConfig objects or dictionaries
        max_workers: Maximum number of parallel workers (default: 4)
        batt_degradation_cost: Battery degradation cost per kWh (default: 0.01)
        timeout: Maximum time in seconds for each optimization (optional)

    Returns:
        Dictionary mapping customer_id to their results and status:
        {
            'customer_id_1': {
                'results': {...},
                'status': {...}
            },
            'customer_id_2': {...},
            ...
        }
    """
    results = {}

    if not customer_configs:
        logger.warning("No customer configurations provided")
        return results

    logger.info(f"Starting batch dispatch for {len(customer_configs)} customers with {max_workers} workers")

    def process_customer(config: Union[CustomerConfig, dict]) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Process a single customer configuration."""
        # Convert dict to CustomerConfig if needed
        if isinstance(config, dict):
            try:
                customer_config = CustomerConfig(**config)
            except Exception as e:
                customer_id = config.get('customer_id', 'unknown')
                logger.error(f"Failed to parse config for customer {customer_id}: {e}")
                return customer_id, {}, {'status': 'failed', 'error': str(e), 'success': False}
        else:
            customer_config = config

        customer_id = customer_config.customer_id

        try:
            # Run optimization
            res, status = run_multi_asset_dispatch(
                customer_config=customer_config,
                batt_degradation_cost=batt_degradation_cost
            )
            return customer_id, res, status

        except Exception as e:
            logger.error(f"Error processing customer {customer_id}: {e}")
            return customer_id, {}, {'status': 'failed', 'error': str(e), 'success': False}

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_customer = {
            executor.submit(process_customer, config): config
            for config in customer_configs
        }

        # Process completed tasks
        completed = 0
        failed = 0
        for future in as_completed(future_to_customer):
            try:
                customer_id, res, status = future.result()
                results[customer_id] = {
                    'results': res,
                    'status': status
                }
                if status.get('success', False):
                    completed += 1
                else:
                    failed += 1
            except Exception as e:
                config = future_to_customer[future]
                customer_id = config.customer_id if isinstance(config, CustomerConfig) else config.get('customer_id', 'unknown')
                results[customer_id] = {
                    'results': {},
                    'status': {'status': 'failed', 'error': str(e), 'success': False}
                }
                failed += 1

        logger.info(f"Batch dispatch completed: {completed} succeeded, {failed} failed out of {len(customer_configs)}")

    return results

def run_batch_dispatch_sync(
    customer_configs: List[Union[CustomerConfig, dict]],
    batt_degradation_cost: float = 0.01
) -> Dict[str, Dict[str, Any]]:
    """
    Run batch dispatch synchronously (one at a time).

    Useful for debugging or when parallel processing causes issues.

    Args:
        customer_configs: List of CustomerConfig objects or dictionaries
        batt_degradation_cost: Battery degradation cost per kWh

    Returns:
        Dictionary mapping customer_id to their results and status
    """
    results = {}

    for i, config in enumerate(customer_configs):
        logger.info(f"Processing customer {i+1}/{len(customer_configs)}")

        if isinstance(config, dict):
            try:
                customer_config = CustomerConfig(**config)
            except Exception as e:
                customer_id = config.get('customer_id', 'unknown')
                results[customer_id] = {
                    'results': {},
                    'status': {'status': 'failed', 'error': str(e), 'success': False}
                }
                continue
        else:
            customer_config = config

        customer_id = customer_config.customer_id
        try:
            res, status = run_multi_asset_dispatch(
                customer_config=customer_config,
                batt_degradation_cost=batt_degradation_cost
            )
            results[customer_id] = {
                'results': res,
                'status': status
            }
        except Exception as e:
            logger.error(f"Error processing customer {customer_id}: {e}")
            results[customer_id] = {
                'results': {},
                'status': {'status': 'failed', 'error': str(e), 'success': False}
            }

    return results

def get_batch_summary(results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate a summary of batch dispatch results.

    Args:
        results: Dictionary of batch results from run_batch_dispatch

    Returns:
        Summary dictionary with statistics
    """
    total = len(results)
    successful = sum(1 for r in results.values() if r.get('status', {}).get('success', False))
    fallback = sum(1 for r in results.values()
                   if r.get('results', {}).get('fallback', False))
    failed = total - successful - fallback

    # Calculate total objective value
    total_objective = 0.0
    for customer_id, data in results.items():
        if data.get('results', {}).get('objective'):
            total_objective += data['results']['objective']

    # Count asset types across all customers
    asset_type_counts = {}
    for customer_id, data in results.items():
        assets = data.get('results', {}).get('assets', {})
        for asset_id, asset_data in assets.items():
            asset_type = asset_data.get('type', 'Unknown')
            asset_type_counts[asset_type] = asset_type_counts.get(asset_type, 0) + 1

    return {
        'total_customers': total,
        'successful': successful,
        'fallback': fallback,
        'failed': failed,
        'success_rate': successful / total if total > 0 else 0.0,
        'total_objective': total_objective,
        'average_objective': total_objective / successful if successful > 0 else 0.0,
        'asset_type_counts': asset_type_counts,
        'overall_status': 'success' if failed == 0 else
                        'partial_success' if successful > 0 else
                        'complete_failure'
    }