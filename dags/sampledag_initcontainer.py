from datetime import datetime

from airflow import DAG

from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import (
    KubernetesPodOperator,
)

import kubernetes.client.models as k8s

# Informações de montagem da chave privada SSH para git
ssh_private_key_volume_source = k8s.V1SecretVolumeSource(
    # SSH não gosta de permissões que permitem leitura por outros usuários
    default_mode=0o0400,
    secret_name="git-creds",
    # Permissões podem ser alteradas aqui também. Pode ser omitido se todos
    # os valores do secret forem inclusos na raiz da pasta de montagem.
    items=[k8s.V1KeyToPath(key="id_rsa", path=".")]
)

ssh_private_key_volume = k8s.V1Volume(
    name="ssh_private_key_volume",
    secret=ssh_private_key_volume_source,
)

ssh_private_key_volume_mount = k8s.V1VolumeMount(
    name="ssh_private_key_volume",
    mount_path="/ssh_private_key"
)

# Variáveis de ambiente, nesse caso vindo de ConfigMap e de Secret
environment_sources = [
    k8s.V1EnvFromSource(config_map_ref=k8s.V1ConfigMapEnvSource(name='sample_config_map')),
    k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name='sample_secret')),
]

# Variáveis de ambiente para essa DAG específica
environment_variables = [k8s.V1EnvVar(name="SAMPLE_ENV", value="SAMPLE")]

# Informações de volume compartilhado para o container de inicialização do Git
# Ainda tem alguma coisa errada, o Kubernetes reclama de não conseguir criar os volumes
git_empty_dir=k8s.V1EmptyDirVolumeSource()

git_volume = k8s.V1Volume(
    name="git_volume",
    empty_dir=git_empty_dir
)

git_init_volume_mount = k8s.V1VolumeMount(
    name="git_volume",
    mount_path="/git"
)

init_container_volume_mounts = [
    ssh_private_key_volume_mount,
    git_init_volume_mount
]

# Container de inicialização, que deveria fazer o git clone para o volume compartilhado.
init_container = k8s.V1Container(
    name="init-container",
    image="k8s.gcr.io/git-sync:v3.1.6",
    volume_mounts=init_container_volume_mounts,
    args=[
        "--ssh",
        "--repo=git@github.com:target/repo.git",
        "--branch=main"
    ],
)

git_volume_mount = k8s.V1VolumeMount(
    name="git_volume",
    mount_path="/opt/gitstuff"
)

with DAG(
    dag_id="sample_dag_with_init",
    start_date=datetime(2021,1,1),
    schedule_interval=None,
    catchup=False,
    tags=["hello"]
) as dag:
    k = KubernetesPodOperator(
        image="target_registry:5000/target_image:1.0",
        # Secrets necessários para o registro privado da imagem Docker
        image_pull_secrets=[k8s.V1LocalObjectReference(name="registrySecret")],
        name="sample_pod",
        namespace='default',
        task_id="sample_pod",
        volumes=[ssh_private_key_volume],
        volume_mounts=[git_volume_mount],
        init_containers=[init_container]
        env_from=environment_sources,
        # Quando que a imagem deve ser atualizada?
        image_pull_policy="Always",
        # Variáveis de ambiente definidas na hora
        env_vars=environment_variables,
        # Eu só consegui fazer argumentos funcionarem desse jeito...
        # Outra opção seria passar os argumentos por variável de ambiente.
        arguments=["/bin/sh","./entry.sh", "arg1", "arg2", "arg3"]
    )