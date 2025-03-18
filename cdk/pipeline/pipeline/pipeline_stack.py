# Description: Guidance for Building a Real Time Bidder for Advertising on AWS (SO9111). Deploys AWS CodeBuild and CodePipeline that in turn deploys the CFN templates with infra and bidder application on EKS
import os
from aws_cdk import (
    Stack,
    aws_codebuild as cb,
    aws_iam as iam
)

from constructs import Construct
class BuildStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, stage: str="dev" , **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        acc = os.getenv("CDK_DEFAULT_ACCOUNT")
        reg = os.getenv("CDK_DEFAULT_REGION")

        # Get environment-specific context
        env_context = self.node.try_get_context(stage)
        shared_context = self.node.try_get_context('shared')
        
        if not shared_context["REPO_OWNER"]:
            repo_owner = "aws-solutions-library-samples"
        else:
            repo_owner = shared_context["REPO_OWNER"]

        if not shared_context["REPO_NAME"]:
            repo_name = "guidance-for-building-a-real-time-bidder-for-advertising-on-aws"
        else:
            repo_name = shared_context["REPO_NAME"]

        if not shared_context["ROOT_STACK_NAME"]:
            root_stack_name = "aws-rtbkit"
        else:
            # fix for issue #59 - Bucket name that prefixes stack name needs to be lowercase
            # and cannot have underscores
            root_stack_name = shared_context["ROOT_STACK_NAME"].lower().replace("_", "-")
        
        if not shared_context["STACK_VARIANT"]:
            stack_variant = "DynamoDBBasic"
        else:
            stack_variant = shared_context["STACK_VARIANT"]
        
        if not env_context["REPO_BRANCH"]:
            repo_branch = "main"
        else:
            repo_branch = env_context["REPO_BRANCH"]
        

        # fix for issue #79 code commit deprecation
        # the solution now points to the opensource github repo by default
        # customers can update their repo configurations through context variables
        # To provide GitHub credentials, please either go to AWS CodeBuild Console to connect or call ImportSourceCredentials to persist your personal access token. Example:
        # aws codebuild import-source-credentials --server-type GITHUB --auth-type PERSONAL_ACCESS_TOKEN --token <token_value>
        cb_source = cb.Source.git_hub(
            owner=repo_owner,
            repo=repo_name,
            webhook=False,
            branch_or_ref=repo_branch
        )
        # Defines the artifact representing the sourcecode

        rtb_pipeline_role = iam.Role(self, id="rtbkit_codebuild_role", role_name="rtbkit_codebuild_role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal('codebuild.amazonaws.com'),
                iam.ServicePrincipal('codepipeline.amazonaws.com'),
            ),
            path="/rtbkit/"
        )
        # Fix for issue #61
        rtb_pipeline_role = self.add_managed_policies(rtb_pipeline_role)

        cb_project=cb.Project(self, "RTBPipelineProject",
            environment={
                "build_image": cb.LinuxBuildImage.AMAZON_LINUX_2_ARM_3,
                "privileged": True,
            },
            environment_variables={
                "AWS_ACCOUNT_ID": cb.BuildEnvironmentVariable(value=acc),
                "RTBKIT_ROOT_STACK_NAME": (cb.BuildEnvironmentVariable(value=root_stack_name)),
                "RTBKIT_VARIANT": cb.BuildEnvironmentVariable(value=stack_variant),
            },
            source=cb_source,
            role=rtb_pipeline_role,
        )
        
        cb.Project.start_build(self, id="RTBBuild", project=cb_project)

        # https://stackoverflow.com/questions/63659802/cannot-assume-role-by-code-pipeline-on-code-pipeline-action-aws-cdk
        cfn_build = cb_project.node.default_child
        cfn_build.add_override("Properties.Environment.Type", "ARM_CONTAINER")
    
    # fix for issue #61
    def add_managed_policies(self, iamrole: iam.Role) -> iam.Role:
        """
        loops through the list of role arns and add it to the input role object and retuns the same back
        """
        managed_policy_arns={"arn:aws:iam::aws:policy/AdministratorAccess",
                    "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
                    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
                    "arn:aws:iam::aws:policy/AmazonKinesisFullAccess",
                    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
                    "arn:aws:iam::aws:policy/AmazonVPCFullAccess",
                    "arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess",
                    "arn:aws:iam::aws:policy/AWSCloudFormationFullAccess"}
        
        for i,arn in enumerate(managed_policy_arns):
            mananged_policy = iam.ManagedPolicy.from_managed_policy_arn(
                scope=self,
                id=f"rtbkit_admin_policy_{i}",
                managed_policy_arn=arn
            )
            iamrole.add_managed_policy(mananged_policy)

        return iamrole