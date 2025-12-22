#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "rich",
# ]
# ///

"""Ping tool.

Used for testing ping to modem, router and Internet
"""

import argparse
import multiprocessing
import os
import re
import subprocess
import sys

from rich.console import Console
from rich.table import Table

# --- Configuration ---
HOSTS = {
    # "Modem": "192.168.100.1",
    "Modem": "10.0.0.1",
    "Router": "192.168.1.1",
    "Google DNS": "8.8.8.8",
}

# Desired display order for results
DISPLAY_ORDER = ["Router", "Modem", "Google DNS"]

# --- Functions ---


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="A concurrent ping tool to diagnose network latency.")
    parser.add_argument(
        "-c", "--count", type=int, default=10, help="The number of ping packets to send to each host. Defaults to 10."
    )
    return parser.parse_args()


def parse_ping_output(ping_output):
    """Parses the output of the ping command to extract key statistics.

    This function is designed for the output format of ping on macOS (darwin).
    If parsing fails, it returns error strings.
    """
    packet_loss_re = re.search(r"(\d+\.?\d*)% packet loss", ping_output)
    packet_stats_re = re.search(r"(\d+) packets transmitted, (\d+) packets received", ping_output)
    rtt_re = re.search(r"round-trip min/avg/max/stddev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", ping_output)
    # Count "Request timeout" occurrences
    timeout_count = len(re.findall(r"Request timeout for icmp_seq", ping_output))

    if packet_loss_re:
        packet_loss = float(packet_loss_re.group(1))
    else:
        packet_loss = "Error"  # Indicate a parsing failure
    if packet_stats_re:
        transmitted = int(packet_stats_re.group(1))
        received = int(packet_stats_re.group(2))
        # if transmitted > 0:
        #     packet_loss = ((transmitted - received) / transmitted) * 100
        # else:
        #     packet_loss = 0.0  # No packets transmitted means 0% loss
    else:
        transmitted = "N/A"
        received = "N/A"

    if rtt_re:
        rtt_stats = {
            "min": rtt_re.group(1),
            "avg": rtt_re.group(2),
            "max": rtt_re.group(3),
            "stddev": rtt_re.group(4),
        }
    else:
        rtt_stats = {"min": "N/A", "avg": "N/A", "max": "N/A", "stddev": "N/A"}

    return {
        "packets_transmitted": transmitted,
        "packets_received": received,
        "packet_loss": packet_loss,
        "rtt_min": rtt_stats["min"],
        "rtt_avg": rtt_stats["avg"],
        "rtt_max": rtt_stats["max"],
        "rtt_stddev": rtt_stats["stddev"],
        "timeout_count": timeout_count,
    }


def ping_host(host_info):
    """Pings a single host and returns its name, IP, and raw output.

    Unpacks a tuple containing ((name, ip), count).
    """
    (name, ip), count = host_info
    print(f"Pinging {name} ({ip})...")
    try:
        # The -W flag sets a timeout in milliseconds for each ping response.
        # This is for GNU/Linux ping. For macOS, we use -t for timeout in seconds for the whole command.
        str(count + 5)  # Whole command timeout for macOS

        command = ["ping", "-c", str(count), ip]
        if sys.platform != "darwin":
            # On Linux, -W is a per-ping timeout, which is not what we want for total runtime.
            # We will use subprocess timeout instead.
            pass

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=count + 10,  # A generous overall timeout for the subprocess
        )
        return name, ip, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return name, ip, f"Ping command timed out after {count + 10} seconds."
    except Exception as e:
        return name, ip, f"An error occurred: {e}"


def main():
    """Main function to run the concurrent ping tests."""
    args = parse_args()

    # Prepare arguments for the multiprocessing pool
    ping_tasks = [((name, ip), args.count) for name, ip in HOSTS.items()]

    console = Console()

    # --- Added: Print current time ---
    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"[bold blue]Ping test started at: {now}[/bold blue]")
    # ------------------------------------

    console.print(f"Starting ping test ({args.count} packets each to {len(HOSTS)} hosts)...")

    # Create a directory for the logs if it doesn't exist
    log_dir = "ping_logs"
    os.makedirs(log_dir, exist_ok=True)

    all_results = []
    with multiprocessing.Pool(processes=len(HOSTS)) as pool:
        # Using imap_unordered to get results as they complete, providing real-time feedback
        for result in pool.imap_unordered(ping_host, ping_tasks):
            name, ip, output = result
            console.print(f"  -> Finished pinging {name} ({ip}).")

            # Save raw output to a file
            filename = os.path.join(log_dir, f"{name.replace(' ', '_')}_ping_results.txt")
            with open(filename, "w") as f:
                f.write(f"--- Ping results for {name} ({ip}) ---\n\n")
                f.write(output)

            # Parse and store results for the summary table
            parsed_data = parse_ping_output(output)
            all_results.append({"name": name, "ip": ip, **parsed_data})

    table = Table(title="Ping Results Summary", show_header=True, header_style="bold magenta")

    table.add_column("Target", style="cyan", no_wrap=True)
    table.add_column("IP Address", style="cyan")
    table.add_column("Transmitted", justify="right")
    table.add_column("Received", justify="right")
    table.add_column("Packet Loss (%)", justify="right")
    table.add_column("Timeouts", justify="right")
    table.add_column("RTT Min", justify="right")
    table.add_column("RTT Avg", justify="right")
    table.add_column("RTT Max", justify="right")
    table.add_column("RTT StdDev", justify="right")

    # Sort results for consistent output: Router, Modem, Google DNS
    all_results.sort(key=lambda x: DISPLAY_ORDER.index(x["name"]))

    # Data
    for res in all_results:
        if isinstance(res["packet_loss"], float):
            loss_str = f"{res['packet_loss']:.1f}"
            if res["packet_loss"] > 5:
                loss_str = f"[red]{loss_str}[/red]"
            elif res["packet_loss"] > 0:
                loss_str = f"[yellow]{loss_str}[/yellow]"
            else:
                loss_str = f"[green]{loss_str}[/green]"
        else:
            loss_str = f"[red]{res['packet_loss']}[/red]"

        timeout_count_str = str(res["timeout_count"])
        if res["timeout_count"] > 0:
            timeout_count_str = f"[yellow]{timeout_count_str}[/yellow]"

        table.add_row(
            res["name"],
            res["ip"],
            str(res["packets_transmitted"]),
            str(res["packets_received"]),
            loss_str,
            timeout_count_str,
            res["rtt_min"],
            res["rtt_avg"],
            res["rtt_max"],
            res["rtt_stddev"],
        )

    console.print(table)
    console.print(f"\n[bold green]Detailed logs have been saved to the '{log_dir}' directory.[/bold green]")


if __name__ == "__main__":
    main()
