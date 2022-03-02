import json
import boto3
import uuid
import time

class glueutil:
    
    def __init__(self, aws_region, accountid):
        session = boto3.Session(region_name=aws_region)
        
        self.region_name = aws_region
        self.ec2_resource = session.resource("ec2")
        self.ec2_client = session.client("ec2")
        self.glue_client = session.client("glue")
        self.iam = boto3.client('iam')
        self.s3 = boto3.resource('s3')

        self.etlid = str(uuid.uuid4())
        
        print(self.etlid)
        self.etlformatted = self.etlid.replace("-","")
        self.accountid = accountid
        
    
    def setupiamrole(self):

        # Create a policy
        my_managed_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "neptune-db:connect",
                    "Resource": f"arn:aws:neptune-db:us-west-2:{self.accountid}:*/*",
                    "Effect": "Allow"
                }
            ]
        }

        policyRef = self.iam.create_policy(
          PolicyName='Glue-Neptune-Policy' + self.etlformatted,
          PolicyDocument=json.dumps(my_managed_policy)
        )
        
        print(policyRef)
        
        
        self.glueNeptuneRole = 'Glue-Neptune-Role' + self.etlformatted

        assumerole_policy = {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {
                                        "Service": [
                                            "glue.amazonaws.com"
                                        ]
                                    },
                                    "Action": [
                                        "sts:AssumeRole"
                                    ]
                                }
                            ]
                        }

        role = self.iam.create_role(
            RoleName=self.glueNeptuneRole,
            AssumeRolePolicyDocument= json.dumps(assumerole_policy),
            Description='Role to give Glue Job permission to Neptune and S3 bucket'
        )


        self.iam.attach_role_policy(
            PolicyArn= policyRef['Policy']['Arn'],
            RoleName=self.glueNeptuneRole
        )

        self.iam.attach_role_policy(
            PolicyArn= "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole",
            RoleName=self.glueNeptuneRole
        )

        self.iam.attach_role_policy(
            PolicyArn= "arn:aws:iam::aws:policy/AmazonS3FullAccess",
            RoleName=self.glueNeptuneRole
        )

        self.iamroleArn = role['Role']['Arn']
        print(self.iamroleArn)
    
        self.iamrole = role['Role']['RoleName']
        print(self.iamrole)
        
        
    
    def setassumerole(self):
        
        assumerole_policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {
                                "Service": [
                                    "glue.amazonaws.com"
                                ]
                            },
                            "Action": [
                                "sts:AssumeRole"
                            ]
                        },
                        {
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": self.iamroleArn  
                            },
                            "Action": [
                                "sts:AssumeRole"
                            ]
                        }
                    ]
                }

        self.iam.update_assume_role_policy(
            RoleName= self.glueNeptuneRole,
            PolicyDocument=json.dumps(assumerole_policy)
        )
        
    def setdefaultvalues(self, s3bucket, glue_database_name, jobs,db_vpc_id,dbsecuritygroup, neptune_endpoint):
        
        self.s3_bucket = s3bucket
        self.glue_database_name = glue_database_name + self.etlformatted
        self.jobs = jobs
        self.db_vpc_id = db_vpc_id
        self.dbsecuritygroup = dbsecuritygroup
        self.neptune_endpoint = neptune_endpoint
       
        
    def setupgluejob(self):
    
        self.glue_client.create_database(
            DatabaseInput={
                "Name": self.glue_database_name,
                "Description": "Database to define tables for glue jobs"
            }
        )
        
        table_descriptions = {
            "demographics": [ 
                        {"Name":"id", "Type":"string"}, 
                        {"Name":"name", "Type":"string"}, 
                        {"Name":"phone", "Type":"string"}, 
                        {"Name":"email", "Type":"string"}, 
                        {"Name":"city", "Type":"string"}, 
                        {"Name":"state", "Type":"string"}, 
                        {"Name":"country", "Type":"string"}, 
                        {"Name":"pincode", "Type":"string"}, 
                        {"Name":"address", "Type":"string"}, 
                        {"Name":"joinedDate", "Type":"string"}, 
                        {"Name":"updatedDate", "Type":"string"}
            ],
            "telemetry": [ 
                        {"Name":"session_id", "Type":"string"}, 
                        {"Name":"user_id", "Type":"string"}, 
                        {"Name":"user_agent", "Type":"string"}, 
                        {"Name":"ip_address", "Type":"string"}, 
                        {"Name":"siteid", "Type":"string"}, 
                        {"Name":"pageid", "Type":"string"}, 
                        {"Name":"session_start", "Type":"string"}
            ],
            "transactions":[ 
                        {"Name":"transaction_id", "Type":"string"}, 
                        {"Name":"user_id", "Type":"string"}, 
                        {"Name":"product_id", "Type":"string"}, 
                        {"Name":"product_name", "Type":"string"}, 
                        {"Name":"purchased_date", "Type":"string"},
                        {"Name":"review", "Type":"string"}
            ]     
        }
        
        for job in self.jobs:
            self.s3.meta.client.upload_file('source/' + job + "/" + job +'.csv', self.s3_bucket,                                 
                                       'data/' + job + "/" + job +'.csv')
            self.s3.meta.client.upload_file('script/neptune-glue-' + job + '.py', self.s3_bucket,                                 
                                       'script/neptune-glue-' + job + self.etlformatted + '.py')
            
        self.s3.meta.client.upload_file('lib/neptune_python_utils.zip', self.s3_bucket, 'lib/neptune_python_utils.zip') 
            
        for job in self.jobs:
            self.glue_client.create_table(
                DatabaseName= self.glue_database_name,
                    TableInput={
                        'Name': job,
                        'Description': job,
                        'StorageDescriptor': {
                            "Columns": table_descriptions[job],
                            "Location": "s3://" + self.s3_bucket + "/data/"+ job + "/",
                            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                            "SerdeInfo":{ 
                                "SerializationLibrary":"org.apache.hadoop.hive.serde2.OpenCSVSerde",
                                "Parameters":{ 
                                    "separatorChar":",",
                                    "quoteChar":"\""
                                }
                            }
                        },
                        "Parameters":{ 
                            "skip.header.line.count":"1"
                        } 
                    }
                )
            

    def setupglueconnections(self):
        subnet_ids = []

        for vpc in self.ec2_resource.vpcs.all():
            if vpc.id == self.db_vpc_id:
                for subnet in vpc.subnets.all():
                    subnet_ids.append(subnet.id)


        subnets = self.ec2_client.describe_subnets(SubnetIds=subnet_ids)

        # create connection objects from subnets
        self.connections = []

        for subnet in subnets["Subnets"]:
            connectionName = self.etlformatted + "-" +  subnet["SubnetId"]

            response = self.glue_client.create_connection(
                ConnectionInput={
                    'Name': connectionName,
                    'Description': self.neptune_endpoint,
                    'ConnectionType': 'NETWORK',
                    'ConnectionProperties': {},
                    'PhysicalConnectionRequirements': {
                        'SubnetId': subnet["SubnetId"],
                        'SecurityGroupIdList': [
                            self.dbsecuritygroup,
                        ],
                        'AvailabilityZone': subnet["AvailabilityZone"]
                    }
                }
            )

            self.connections.append({"connectionName": connectionName, "subnet": subnet["AvailabilityZone"]})




    def updategluejobwithconnection(self,glueconnection):
        
        s3bucketfullpath = "s3://" + self.s3_bucket + "/"

        for job in self.jobs:
            response = self.glue_client.create_job(
                Name= "job_" + job + self.etlformatted,
                Description= job + self.etlformatted,
                Role= self.iamrole,
                ExecutionProperty={
                    'MaxConcurrentRuns': 123
                },
                Command={
                    'Name': 'glueetl',
                    'ScriptLocation': s3bucketfullpath + "script/neptune-glue-"+ job + self.etlformatted + ".py",
                    'PythonVersion': '3'
                },
                DefaultArguments={
                    '--additional-python-modules': s3bucketfullpath + 'lib/neptune_python_utils.zip',
                    '--extra-py-files': s3bucketfullpath + 'lib/neptune_python_utils.zip',
                    '--NEPTUNE_CONNECTION_NAME': glueconnection,
                    '--DATABASE_NAME': self.glue_database_name,
                    '--CONNECT_TO_NEPTUNE_ROLE_ARN': self.iamroleArn,
                    '--AWS_REGION':'us-west-2'

                },
                NonOverridableArguments={},
                Connections={
                    'Connections': [glueconnection]
                },
                MaxRetries=0,
                Timeout=123,
                GlueVersion='2.0',
                NumberOfWorkers=123,
                WorkerType='G.2X'
            )
        
 

    def startjob(self,jobname):
        
        startjobresponse = self.glue_client.start_job_run(
            JobName= jobname + self.etlformatted
        )
        
        return startjobresponse
    
    
    def checkjobstatus(self,jobname,jobrunid):
        
        while 1==1:
            getjobrunresponse = self.glue_client.get_job_run(
                JobName=jobname + self.etlformatted,
                RunId=jobrunid
            )

            print(getjobrunresponse['JobRun']['JobRunState'])

            if((getjobrunresponse['JobRun']['JobRunState'] == 'SUCCEEDED') 
               or (getjobrunresponse['JobRun']['JobRunState'] == 'FAILED')):
                break;
            else:
                print("Retrying after 60 sec")
                time.sleep(60)