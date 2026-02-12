#!/usr/bin/env python
"""
Subscription Renewal Notification Scheduler

This script can be run as a cron job to automatically send renewal notifications.
It supports time-based filtering to send notifications at the exact time subscriptions end.

Example cron jobs:
# Run every hour to check for time-specific notifications
0 * * * * cd /path/to/your/project && python scheduler.py --time-based

# Run daily at 3 PM for general notifications
0 15 * * * cd /path/to/your/project && python scheduler.py

For Windows Task Scheduler, create tasks that run this script at different times.
"""

import os
import sys
import django
import argparse
from datetime import datetime, time

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subly.settings')
django.setup()

from subscriptions.services import NotificationService
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('renewal_notifications.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Main function to send renewal notifications"""
    parser = argparse.ArgumentParser(description='Send subscription renewal notifications')
    parser.add_argument(
        '--time-based', 
        action='store_true',
        help='Send notifications based on current time (matches subscription renewal times)'
    )
    parser.add_argument(
        '--days-before',
        type=int,
        default=3,
        help='Number of days before renewal to send notification (default: 3)'
    )
    
    args = parser.parse_args()
    
    logger.info("Starting renewal notification scheduler")
    
    try:
        # Determine target time for filtering
        target_time = None
        if args.time_based:
            # Use current time for filtering
            target_time = datetime.now().time()
            logger.info(f"Using time-based filtering: {target_time.strftime('%I:%M %p')}")
        
        # Send notifications based on per-subscription offsets
        results = NotificationService.send_batch_notifications(
            target_time=target_time
        )
        
        logger.info(f"Notification batch completed:")
        logger.info(f"  Total subscriptions checked: {results['total']}")
        logger.info(f"  Notifications sent: {results['sent']}")
        logger.info(f"  Errors: {results['errors']}")
        
        if args.time_based:
            logger.info(f"  Time filter applied: {target_time.strftime('%I:%M %p')}")
        
        if results['errors'] > 0:
            logger.warning(f"There were {results['errors']} errors during notification sending")
            sys.exit(1)
        else:
            logger.info("All notifications sent successfully")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Scheduler failed with error: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()