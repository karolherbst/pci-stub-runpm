#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/module.h>
#include <linux/pci.h>
#include <linux/pm.h>
#include <linux/pm_runtime.h>

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Module for debugging runpm issues");
MODULE_AUTHOR("Karol Herbst <kherbst@redhat.com>");
MODULE_VERSION("0.1");

struct pci_strub_runpm_data {
	
};

static int
pci_stub_runpm_probe(struct pci_dev *pdev, const struct pci_device_id *id)
{
	int ret;
	resource_size_t start;
	resource_size_t size;

	pci_ignore_hotplug(pdev);

	/* clear error state */
	pm_runtime_use_autosuspend(&pdev->dev);
	pm_runtime_set_autosuspend_delay(&pdev->dev, 2000);
	pm_runtime_set_active(&pdev->dev);
	pm_runtime_allow(&pdev->dev);
	pm_runtime_mark_last_busy(&pdev->dev);
	pm_runtime_put(&pdev->dev);

	printk(KERN_INFO "dev->pm.usage_count: %u\n",
	       atomic_read(&pdev->dev.power.usage_count));

	ret = pci_enable_device(pdev);
	if (ret)
		return ret;

	start = pci_resource_start(pdev, 0);
	size = pci_resource_len(pdev, 0);

	pci_set_master(pdev);

	return 0;
}

static void
pci_stub_runpm_remove(struct pci_dev *pdev)
{
	pci_disable_device(pdev);

	printk(KERN_INFO "dev->pm.usage_count: %u\n",
	       atomic_read(&pdev->dev.power.usage_count));
}

static int
pci_stub_runpm_runtime_suspend(struct device *dev) {
	struct pci_dev *pdev = to_pci_dev(dev);
	pci_disable_device(pdev);
	return 0;
}

static int
pci_stub_runpm_runtime_resume(struct device *dev) {
	int ret;
	struct pci_dev *pdev = to_pci_dev(dev);

	if (pdev->current_state != PCI_D0) {
		printk(KERN_ERR "device not in D0 state. Aborting resume!\n");
		return -EIO;
	}

	ret = pci_enable_device(pdev);
	if (ret)
		return ret;

	pci_set_master(pdev);
	return 0;
}

static struct dev_pm_ops pci_stub_runpm_ops = {
	.runtime_suspend = pci_stub_runpm_runtime_suspend,
	.runtime_resume = pci_stub_runpm_runtime_resume,
};

static struct pci_device_id pci_stub_runpm_pci_device_id = {
	.vendor = 0x10de,
	.device = PCI_ANY_ID,
	.subvendor = PCI_ANY_ID,
	.subdevice = PCI_ANY_ID,
	.class = PCI_BASE_CLASS_DISPLAY << 16,
	.class_mask = 0xff0000,
};

static struct pci_driver pci_stub_runpm_pci_driver = {
	.name = KBUILD_MODNAME,
	.probe = pci_stub_runpm_probe,
	.remove = pci_stub_runpm_remove,
	.id_table = &pci_stub_runpm_pci_device_id,
	.driver = {
		.pm = &pci_stub_runpm_ops,
	},
};

static int __init
on_init(void) {
	int ret = pci_register_driver(&pci_stub_runpm_pci_driver);
	if (ret)
		return ret;

	return ret;
}

static void __exit
on_exit(void) {
	pci_unregister_driver(&pci_stub_runpm_pci_driver);
}

module_init(on_init);
module_exit(on_exit);
