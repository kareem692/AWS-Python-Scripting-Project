import boto3


#Create session and clients
aws_session=boto3.session.Session(profile_name="python",region_name="us-east-1")
client  = aws_session.client('ec2',region_name="us-east-1")
ec2_resource = aws_session.resource("ec2", region_name="us-east-1")

#Create VPC
Custom_VPC = client.create_vpc(CidrBlock='10.0.0.0/16')
Custom_VPC_ID=Custom_VPC['Vpc']['VpcId']
print(f"New VPC has been created successfully with id {Custom_VPC_ID}")

#Create subnets
public_subnet1 = client.create_subnet(AvailabilityZone='us-east-1a',CidrBlock='10.0.10.0/24',VpcId='vpc-06bbf3339855c8a1d',)
public_subnet_ID1=public_subnet1['Subnet']['SubnetId']
private_subnet1 = client.create_subnet(AvailabilityZone='us-east-1a',CidrBlock='10.0.100.0/24',VpcId='vpc-06bbf3339855c8a1d',)
private_subnet_ID1=private_subnet1['Subnet']['SubnetId']
public_subnet2 = client.create_subnet(AvailabilityZone='us-east-1b',CidrBlock='10.0.20.0/24',VpcId='vpc-06bbf3339855c8a1d',)
public_subnet_ID2=public_subnet2['Subnet']['SubnetId']
private_subnet2= client.create_subnet(AvailabilityZone='us-east-1b',CidrBlock='10.0.200.0/24',VpcId='vpc-06bbf3339855c8a1d',)
private_subnet_ID2=private_subnet2['Subnet']['SubnetId']

public_subnets_list=[
    public_subnet_ID1,
    public_subnet_ID2,
]

private_subnets_list=[
    private_subnet_ID1,
    private_subnet_ID2
]

#Enable auto-assign public IP addresses for public subnets
for subnet_id in public_subnets_list:
    client.modify_subnet_attribute(
        SubnetId=subnet_id, MapPublicIpOnLaunch={'Value': True})

#Create IGW
IGW = client.create_internet_gateway()
internet_gateway_id = IGW['InternetGateway']['InternetGatewayId']
print(f"Internet Gateway has been created successfully , its id is {internet_gateway_id}")


#Create route table for public subnets to route traffic through Internet Gateway
New_RT = client.create_route_table(VpcId=Custom_VPC_ID)
public_route_table_id = New_RT['RouteTable']['RouteTableId']
print(f"The New Route Table for public subnets have been created successfully with id {public_route_table_id}")
for subnet_id in public_subnets_list:
  response = client.associate_route_table(
    RouteTableId=public_route_table_id,
    SubnetId=subnet_id
  )

#add the default route in public route table towards Internet Gateway
route_table = ec2_resource.RouteTable(public_route_table_id)
route_table.create_route(
    DestinationCidrBlock='0.0.0.0/0', GatewayId=internet_gateway_id)

#Create NAT
allocation = client.allocate_address(Domain='vpc')  # Allocates an Elastic IP address to NAT Gateway
NAT = client.create_nat_gateway(AllocationId=allocation['AllocationId'], SubnetId=public_subnets_list[0])
nat_gateway_id = NAT['NatGateway']['NatGatewayId']
print(f"NAT Gateway has been created successfully , its id is {nat_gateway_id}")

#Create route table for private subnets to route traffic through NAT Gateway
New_RT = client.create_route_table(VpcId=Custom_VPC_ID)
private_route_table_id = New_RT['RouteTable']['RouteTableId']
print(
    f"The New Route Table for Private subnets have been created successfully with id {private_route_table_id}")

#Associate private subnets to private route table
for subnet_id in private_subnets_list:
    responses = client.associate_route_table(
        RouteTableId=private_route_table_id,
        SubnetId=subnet_id
    )

'''13 - Ensuring NAT Gateway is up and available '''
waiter = client.get_waiter('nat_gateway_available')
print("NAT Gateway is being started......")
waiter.wait(NatGatewayIds=[nat_gateway_id, ])
print("NAT Gateway is now up and available ")

#add the default route in private route table towards NAT Gateway
route_table = ec2_resource.RouteTable(private_route_table_id)
route_table.create_route(
    DestinationCidrBlock='0.0.0.0/0', NatGatewayId=nat_gateway_id)

#Create the required security group for EC2 instances.
Private_SG = client.create_security_group(
    Description='Private SG for EC2 Instances',
    GroupName='Private_SG',
    VpcId=Custom_VPC_ID,
    TagSpecifications=[
        {
            'ResourceType': 'security-group',
            'Tags': [
                {
                    'Key': 'Name',
                    'Value': 'WebSG'
                },
            ]
        },
    ],
)

WebSG_ID = Private_SG['GroupId']
print(f"Security Group WebSG has been created successfully , its id is {WebSG_ID}")

#Add security group ingress rules for ports [22,80,443]
responsed = client.authorize_security_group_ingress(
    GroupId=WebSG_ID,
    IpPermissions=[
        {
            'FromPort': 22,
            'IpProtocol': 'tcp',
            'IpRanges': [
                {
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'SSH access',
                },
            ],
            'ToPort': 22,
        },
        {
            'FromPort': 80,
            'IpProtocol': 'tcp',
            'IpRanges': [
                {
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'HTTP access',
                },
            ],
            'ToPort': 80,
        },
        {
            'FromPort': 443,
            'IpProtocol': 'tcp',
            'IpRanges': [
                {
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'Secure HTTP access',
                },
            ],
            'ToPort': 443,
        },
    ],
)
#add egress rule to the WebSG - allowing traffic for updates and download any required packages.
client.authorize_security_group_egress(
    GroupId=WebSG_ID,
    IpPermissions=[
        {
            'FromPort': 0,
            'IpProtocol': 'tcp',
            'IpRanges': [
                {
                    'CidrIp': '0.0.0.0/0',
                },
            ],
            'ToPort': 0,
        },
    ],
)
#Launch EC2 instances in private subnets
user_data_script1 = '''#!/bin/bash
yum update -y
yum install httpd -y
systemctl start httpd
systemctl enable httpd
echo "This is server *1* in AWS Region US-EAST-1 in AZ US-EAST-1A" > /var/www/html/index.html
'''
user_data_script2 = '''#!bin/bash
yum update -y
yum install httpd -y
systemctl start httpd# starts httpd service   
systemctl enable httpd# enable httpd to auto-start at system boot
echo " This is server *2* in AWS Region US-EAST-1 in AZ US-EAST-1B " > /var/www/html/index.html
'''
user_data_scripts = [user_data_script1, user_data_script2]

instance_ids = []
for subnet_id, user_data_script in zip(private_subnets_list, user_data_scripts):
    response = client.run_instances(
        ImageId='ami-0889a44b331db0194',  # Specify the AMI that is suitable in each region.
        InstanceType='t2.micro',  # Specify the desired instance type
        KeyName='MyKey',  # choose a name for existing Key-Pair name
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet_id,
        UserData=user_data_script,
        BlockDeviceMappings=[
            {
                'DeviceName': '/dev/xvda',
                'Ebs': {
                    'DeleteOnTermination': True,
                    'Encrypted': True,
                    'VolumeSize': 8,
                    'VolumeType': 'gp2'
                }
            }
        ],
        # Specify the security group ID for the instances
        SecurityGroupIds=[WebSG_ID,]
    )
    instance_ids.append(response['Instances'][0]['InstanceId'])

'''Ensuring all instances are in running State'''
waiter = client.get_waiter('instance_running')
print("Web and Application instances are being started ......")
waiter.wait(InstanceIds=instance_ids)
print("All Instances are running now")
print(
    f"The new instances for Web and App have been created successfully, their ids are {instance_ids[0]} and {instance_ids[1]}")

'''Create Client Objects for other Services like Load Balancer , Auto Scaling, RDS'''
# A- Create a client Object for Elastic Load Balancing
elb_client = aws_session.client('elbv2', region_name='us-east-1')

# B- Create a client object for Auto Scaling
autoscaling_client = aws_session.client('autoscaling', region_name='us-east-1')

# C- Create a client for RDS
rds_client = aws_session.client('rds', region_name='us-east-1')

#Create a target group
response = elb_client.create_target_group(
    Name='webTG',
    Protocol='HTTP',
    Port=80,
        VpcId=Custom_VPC_ID,
    HealthCheckProtocol='HTTP',
    HealthCheckPort='80',
    HealthCheckEnabled=True

)
target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
print(f"The Target Group has been created successfully , its arn is {target_group_arn}")

#Register EC2-targets to the target group
elb_client.register_targets(
    TargetGroupArn=target_group_arn,
    Targets=[
        {'Id': instance_id, 'Port': 80} for instance_id in instance_ids
    ]
)

'''Create an application load balancer '''
# A- Create the Load balancer Security Group
ALB_SG = client.create_security_group(
    Description='SG for Load Balancer',
    GroupName='ALBSG',
    VpcId=Custom_VPC_ID,
    TagSpecifications=[
        {
            'ResourceType': 'security-group',
            'Tags': [
                {
                    'Key': 'Name',
                    'Value': 'ALBSG'
                },
            ]
        },
    ],
)
ALB_SG_ID = ALB_SG['GroupId']
print(f"Security Group ALB_SG for Application Load Balancer has been created successfully , its id is {ALB_SG_ID}")

# B- add ingress rule to the ALB SG , allowing HTTP Traffic inbound
client.authorize_security_group_ingress(
    GroupId=ALB_SG_ID,
    IpPermissions=[
        {
            'FromPort': 80,
            'IpProtocol': 'tcp',
            'IpRanges': [
                {
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'HTTP access',
                },
            ],
            'ToPort': 80,
        },
    ],
)
# C- add egress rules to the ALB SG - allowing outbound port 80 towards WebSG security group
client.authorize_security_group_egress(
    GroupId=ALB_SG_ID,
    IpPermissions=[
        {
            'FromPort': 80,
            'IpProtocol': 'tcp',
            'ToPort': 80,
            'UserIdGroupPairs': [
                {
                    'GroupId': WebSG_ID,
                },
            ],
        },
    ],
)
# D- creating the ALB itself
response = elb_client.create_load_balancer(
    Name='DolfinedLoadBalancer',
    Subnets=public_subnets_list,
    SecurityGroups=[ALB_SG_ID, ],
    Scheme='internet-facing',
    Type='application',
    IpAddressType='ipv4'
)
''' E- Ensuring Load Balancer is available and up '''
load_balancer_arn = response['LoadBalancers'][0]['LoadBalancerArn']
load_balancer_dns = response['LoadBalancers'][0]['DNSName']
waiter = elb_client.get_waiter('load_balancer_available')
print("Application Load Balancer is being started ......")
waiter.wait(LoadBalancerArns=[load_balancer_arn, ])
print("Load Balancer is up and available now")
print(
    f"The Application Load Balancer has been created successfully , its arn is {load_balancer_arn} and its DNS is {load_balancer_dns}")

#Create a listener for the load balancer
elb_client.create_listener(
    LoadBalancerArn=load_balancer_arn,
    Protocol='HTTP',
    Port=80,
    DefaultActions=[{'Type': 'forward', 'TargetGroupArn': target_group_arn}]
)

#Configure the auto-scaling group
# A- Create the Launch Configuration
autoscaling_client.create_launch_configuration(
    ImageId='ami-0889a44b331db0194',
    InstanceType='t2.micro',
    LaunchConfigurationName='my-launch-config',
    SecurityGroups=[WebSG_ID, ],
)

# B- Create the auto-scaling group
autoscaling_client.create_auto_scaling_group(
    AutoScalingGroupName='DolfinedScalingGroup',
    LaunchConfigurationName='my-launch-config',
    MinSize=1,
    MaxSize=3,
    DesiredCapacity=1,
    TargetGroupARNs=[target_group_arn, ],

)
response = autoscaling_client.describe_auto_scaling_groups(AutoScalingGroupNames=['DolfinedScalingGroup', ])
print(
    f"The Auto Scaling Group has been created successfully , its arn is {response['AutoScalingGroups'][0]['AutoScalingGroupARN']}")

'''create the RDS DataBase and its security group'''
# A- Create a DB security group
DB_SG = client.create_security_group(
    Description='SG for Database',
    GroupName='db_SG',
    VpcId=Custom_VPC_ID,
    TagSpecifications=[
        {
            'ResourceType': 'security-group',
            'Tags': [
                {
                    'Key': 'Name',
                    'Value': 'DB_SG'
                },
            ]
        },
    ],
)

DB_SG_ID = DB_SG['GroupId']
print(f"Security Group DB_SG has been created successfully , its id is {DB_SG_ID}")

# B- Authorize inbound access to the DB security group from only WebSG security group
client.authorize_security_group_ingress(
    GroupId=DB_SG_ID,
    IpPermissions=[
        {
            'FromPort': 0,
            'ToPort': 0,
            'IpProtocol': '-1',
            'UserIdGroupPairs': [
                {
                    'GroupId': WebSG_ID,
                },
            ],
        },
    ],
)

# C - Create the DB Subnet Group
rds_client.create_db_subnet_group(
    DBSubnetGroupDescription='RDS Databases Subnet Group',
    DBSubnetGroupName='myrdsdbsubnetgroup',
    SubnetIds=private_subnets_list
)

# D- Launch The Multi-AZ RDS database
response = rds_client.create_db_instance(
    DBInstanceIdentifier='DolfinedDBInstance',
    DBInstanceClass='db.t2.micro',
    Engine='mysql',
    AllocatedStorage=10,
    MasterUsername='admin',
    MasterUserPassword='dolfineddb',
    DBSubnetGroupName='myrdsdbsubnetgroup',
    VpcSecurityGroupIds=[DB_SG_ID, ],
    MultiAZ=True
)
rds_arn = response['DBInstance']['DBInstanceArn']
waiter = rds_client.get_waiter('db_instance_available')
print("RDS Instance is being started ......")
waiter.wait(DBInstanceIdentifier='DolfinedDBInstance')
print("RDS Instance is up and available now")
rds = rds_client.describe_db_instances(DBInstanceIdentifier='DolfinedDBInstance')
rds_address = rds['DBInstances'][0]['Endpoint']['Address']
print(
    f"The RDS Instance DB has been created successfully , its arn is {rds_arn} and its DNS Address is {rds_address}")











