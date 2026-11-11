# Manage the AWS demo server (one t3.small in ap-southeast-2). See deploy/aws.md.
#
#   powershell -ExecutionPolicy Bypass -File deploy\aws.ps1 status     # state + URL
#   ... start | stop                                                    # stop when not demoing
#   ... logs                                                            # first-boot log via SSM
#   ... launch                                                          # create the server (once)
#   ... teardown                                                        # delete everything
#
# Costs come out of the Free plan credits: ~$0.026/h running + $0.005/h public IP,
# and ~$1.92/month for the 20 GB disk even while stopped.

param([Parameter(Mandatory = $true)][ValidateSet("launch", "start", "stop", "status", "logs", "teardown")] [string]$Action)

$ErrorActionPreference = "Stop"
$env:AWS_PROFILE = "ragg"
$env:AWS_REGION = "ap-southeast-2"
$env:AWS_PAGER = ""
$Name = "ragg-app"
$Bucket = "ragg-deploy-885879439469"

function Get-InstanceId {
    aws ec2 describe-instances --filters "Name=tag:Name,Values=$Name" `
        "Name=instance-state-name,Values=pending,running,stopping,stopped" `
        --query "Reservations[].Instances[].InstanceId" --output text
}

function Show-Status($id) {
    $info = aws ec2 describe-instances --instance-ids $id `
        --query "Reservations[0].Instances[0].[State.Name,PublicIpAddress]" --output text
    $state, $ip = $info -split "\s+"
    Write-Host "instance $id is $state"
    if ($state -eq "running" -and $ip -and $ip -ne "None") { Write-Host "open http://$ip/" }
}

$id = Get-InstanceId
switch ($Action) {
    "launch" {
        if ($id) { Write-Host "Already exists: $id"; Show-Status $id; break }
        $ami = aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 `
            --query Parameter.Value --output text
        $sg = aws ec2 describe-security-groups --filters Name=group-name,Values=ragg-web `
            --query "SecurityGroups[0].GroupId" --output text
        $userData = Join-Path $PSScriptRoot "user-data.sh"
        $id = aws ec2 run-instances --image-id $ami --instance-type t3.small --count 1 `
            --iam-instance-profile Name=ragg-ec2-profile --security-group-ids $sg `
            --user-data "file://$userData" `
            --credit-specification CpuCredits=standard `
            --metadata-options "HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled" `
            --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}" `
            --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$Name},{Key=project,Value=ragg}]" `
                                 "ResourceType=volume,Tags=[{Key=Name,Value=$Name},{Key=project,Value=ragg}]" `
            --query "Instances[0].InstanceId" --output text
        Write-Host "launched $id; first boot takes ~5-8 minutes (image pull + database restore)"
        aws ec2 wait instance-running --instance-ids $id
        Show-Status $id
    }
    "start" {
        if (-not $id) { Write-Host "No server. Run: launch"; break }
        aws ec2 start-instances --instance-ids $id | Out-Null
        aws ec2 wait instance-running --instance-ids $id
        Show-Status $id
        Write-Host "the app needs ~1 minute after boot; the first question loads the models (~30 s)"
    }
    "stop" {
        if (-not $id) { Write-Host "No server."; break }
        aws ec2 stop-instances --instance-ids $id | Out-Null
        aws ec2 wait instance-stopped --instance-ids $id
        Write-Host "stopped $id (only the disk is billed now, ~`$1.92/month)"
    }
    "status" {
        if (-not $id) { Write-Host "No server."; break }
        Show-Status $id
    }
    "logs" {
        if (-not $id) { Write-Host "No server."; break }
        $cmd = aws ssm send-command --instance-ids $id --document-name AWS-RunShellScript `
            --parameters 'commands=["tail -n 40 /var/log/ragg-setup.log","docker ps --format \"{{.Names}} {{.Status}}\""]' `
            --query Command.CommandId --output text
        Start-Sleep 4
        aws ssm get-command-invocation --command-id $cmd --instance-id $id --query StandardOutputContent --output text
    }
    "teardown" {
        if ($id) {
            aws ec2 terminate-instances --instance-ids $id | Out-Null
            aws ec2 wait instance-terminated --instance-ids $id
            Write-Host "terminated $id (its disk is deleted with it)"
        }
        $sg = aws ec2 describe-security-groups --filters Name=group-name,Values=ragg-web --query "SecurityGroups[0].GroupId" --output text
        if ($sg -and $sg -ne "None") { aws ec2 delete-security-group --group-id $sg; Write-Host "deleted security group $sg" }
        aws iam remove-role-from-instance-profile --instance-profile-name ragg-ec2-profile --role-name ragg-ec2-role 2>$null
        aws iam delete-instance-profile --instance-profile-name ragg-ec2-profile 2>$null
        aws iam detach-role-policy --role-name ragg-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore 2>$null
        aws iam delete-role-policy --role-name ragg-ec2-role --policy-name ragg-app-read 2>$null
        aws iam delete-role --role-name ragg-ec2-role 2>$null
        Write-Host "deleted IAM role and instance profile"
        aws s3 rm "s3://$Bucket" --recursive --only-show-errors 2>$null
        aws s3api delete-bucket --bucket $Bucket 2>$null
        Write-Host "deleted bucket $Bucket"
        aws ssm delete-parameters --names /ragg/groq_api_key /ragg/anthropic_api_key | Out-Null
        Write-Host "deleted parameters /ragg/*"
    }
}
