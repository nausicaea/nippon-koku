function(source_repo, source_target_revision) 

local namespaces = ["k8s-monitoring"];

local appSpec(namespace, repo, revision) = {
    apiVersion: "argoproj.io/v1alpha1",
    kind: "Application",
    metadata: {
        name: "otel-collectors-" + namespace,
        namespace: "argocd",
        finalizers: ["resources-finalizer.argocd.argoproj.io"],
        annotations: {
            "argocd.argoproj.io/sync-wave": "4",
        },
    },
    spec: {
        project: "appproj-nippon-koku",
        source: {
            repoURL: repo,
            targetRevision: revision,
            path: "manifests/otel-collectors/" + namespace,
        },
        destination: {
            server: "https://kubernetes.default.svc",
            namespace: namespace,
        },
    },
};

[appSpec(n, source_repo, source_target_revision) for n in namespaces]
