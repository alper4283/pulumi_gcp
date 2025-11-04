"""A Google Cloud Python Pulumi program"""
import os
import datetime
import re
import pulumi
import pulumi_gcp as gcp

PUBLIC_KEY = os.getenv("SSH_PUB_KEY", "").strip()

gcp_cfg = pulumi.Config("gcp")
wp_cfg = pulumi.Config("wp")

region = gcp_cfg.require("region")
zone = gcp_cfg.require("zone")
network_name = wp_cfg.require("networkName")
subnet_name = wp_cfg.require("subnetName")
machine_type = wp_cfg.require("machineType")

#Generating a name for the VM
def sanitize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]","-",name)
    name = re.sub(r"-{2,}","-", name).strip("-")
    if not name: name = "wp"
    if not re.match(r"^[a-z]", name): name = "w" + name
    if len(name) > 63: name = name[:63]
    if not re.search(r"[a-z0-9]$", name): name = name[:-1] + "0"
    return name

vm_name_cfg = wp_cfg.get("vmName")
if vm_name_cfg:
    vm_name = sanitize(vm_name_cfg)
else:
    build_no = os.getenv("BUILD_NUMBER")
    if build_no:
        vm_name = sanitize(f"wp-{build_no}")
    else:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        vm_name = sanitize(f"wp-{ts}")

subnet = gcp.compute.get_subnetwork(name=subnet_name, region=region)

address = gcp.compute.Address(
        resource_name=f"{vm_name}-addr",
        name=f"{vm_name}-ip",
        region=region,
        address_type="EXTERNAL",
        network_tier="PREMIUM",
        description=f"Reserved for {vm_name}",
)

instance = gcp.compute.Instance(
        resource_name=vm_name,
        name=vm_name,
        zone=zone,
        machine_type=machine_type,
        tags=["wp-public"],
        metadata={
            "block-project-ssh-keys": "TRUE",
            "ssh-keys": f"debian:{PUBLIC_KEY}",     
        },
        boot_disk=gcp.compute.InstanceBootDiskArgs(
            initialize_params=gcp.compute.InstanceBootDiskInitializeParamsArgs(
                image="debian-cloud/debian-12",
                size=20,
                type="pd-balanced",
            )
        ),
        network_interfaces=[
            gcp.compute.InstanceNetworkInterfaceArgs(
                subnetwork=subnet.self_link,
                access_configs=[
                    gcp.compute.InstanceNetworkInterfaceAccessConfigArgs(
                        nat_ip=address.address,
                        network_tier="PREMIUM",
                    )
                ],
            )
        ],
        service_account=gcp.compute.InstanceServiceAccountArgs(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        ),
        labels={"role": "wordpress-host", "env": "dev"},
)

pulumi.export("vmName", vm_name)
pulumi.export("vmIp", instance.network_interfaces.apply(
    lambda nics: (nics or [])[0].access_configs[0].nat_ip if nics else ""
))

