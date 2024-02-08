#!/usr/bin/env python3 -u
import argparse
import json
import logging
import sys

import yaml


def main(args):
    parser = argparse.ArgumentParser(description="Run asm parser")
    parser.add_argument('--config', type=str, help='Configuration file')
    parser.add_argument('--name', type=str, help='Option block to consider')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger()

    args = parser.parse_args(args)
    if not args.config:
        logger.error('No configuration file specified')
        sys.exit(-1)

    with open(args.config) as fp:
        configs = yaml.safe_load(fp)

    if not args.name:
        logger.error('No job name was specified')
        sys.exit(-1)

    if args.name not in configs:
        logger.error(f'Specified job name {args.name} is not found in configuration')
        sys.exit(-1)

    logger.info(f'Start injection of {args.name} configuration')
    options = configs[args.name]
    for option in options:
        target_file = option['file']

        with open(target_file) as fp:
            if target_file.endswith('json'):
                target_conf = json.load(fp)
            elif target_file.endswith('yml'):
                target_conf = yaml.safe_load(fp)
            else:
                logger.error(f'Unknown target configuration file {target_file}')
                sys.exit(-1)

        target_options = option['options']

        # insert a new option into configuration
        for target_option, val in target_options.items():
            option_path = target_option.split(":")

            cur_conf = target_conf
            for option_item in option_path:
                if option_item != option_path[-1]:
                    if option_item in cur_conf:
                        cur_conf = cur_conf[option_item]
                    else:
                        logger.error(f'{option_item} is not found in configuration')
                        sys.exit(-1)
                else:
                    cur_conf[option_item] = val

        with open(target_file, 'w') as fp:
            if target_file.endswith('json'):
                json.dump(target_conf, fp, indent=2)
            elif target_file.endswith('yml'):
                yaml.dump(target_conf, fp)
            else:
                logger.error(f'Unknown target configuration file {target_file}')
                sys.exit(-1)


if __name__ == "__main__":
    main(sys.argv[1:])
