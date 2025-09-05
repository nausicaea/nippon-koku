function(source_repo, source_target_revision) 

local namespaces = ["kube-system", "longhorn-system", "tailscale", "kubescape"];

local appSpec(namespace, repo, revision) = {
    apiVersion: "argoproj.io/v1alpha1",
    kind: "Application",
    metadata: {
        name: "bootstrap-" + namespace,
        namespace: "argocd",
        finalizers: ["resources-finalizer.argocd.argoproj.io"],
        annotations: {
            "argocd.argoproj.io/sync-wave": "1",
        },
    },
    spec: {
        project: "appproj-nippon-koku",
        source: {
            repoURL: repo,
            targetRevision: revision,
            path: "manifests/bootstrap/" + namespace,
        },
        destination: {
            server: "https://kubernetes.default.svc",
            namespace: namespace,
        },
        syncPolicy: {
          automated: {},
        },
    },
};

[appSpec(n, source_repo, source_target_revision) for n in namespaces]
